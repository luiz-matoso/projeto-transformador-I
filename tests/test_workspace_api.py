import json
import os
import secrets
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from api.config import Settings
from api.main import create_app
from api.storage import WorkspaceStorage
from tests.workspace_fake import SupabaseFake
from tests.test_api import AUTH_ENV, authorize, image_bytes, metadata
from ml.pipeline import INACTIVE_FEATURES
import numpy as np

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        checkpoint = Path(self.temp.name)/"checkpoint.pt"
        checkpoint.write_bytes(b"test-only-checkpoint")
        self.fake = SupabaseFake()
        self.store = WorkspaceStorage("https://supabase.test", secrets.token_urlsafe(), transport=httpx.MockTransport(self.fake))
        self.env = patch.dict(os.environ, AUTH_ENV);self.env.start();self.addCleanup(self.env.stop)
        self.factory = patch("api.main.WorkspaceStorage.from_env", return_value=self.store);self.factory.start();self.addCleanup(self.factory.stop)
        self.models = patch("api.main.load_components", return_value=(None,None,None,None,"cpu",{}));self.models.start();self.addCleanup(self.models.stop)
        def scene(image, **kwargs):
            return {"mask":np.ones((image.height,image.width),dtype=np.uint8),"features":{"passage_width":"adequate","obstruction":"none","surface_condition":"regular","level_change":"none","path_continuity":"continuous"},"predictions":{},"not_modeled":{},"inactive_features":list(INACTIVE_FEATURES),"observation":kwargs["observation"]}
        self.vision = patch("api.routes.transitability.observe_scene", side_effect=scene);self.mock_vision=self.vision.start();self.addCleanup(self.vision.stop)
        self.client=TestClient(create_app(Settings(segformer_checkpoint=checkpoint,dino_checkpoint=checkpoint)))
        self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None);authorize(self.client)
        self.profile={"id":str(uuid4()),"name":"Functional example","requirements":metadata()["profiles"][0]}

    def analysis(self, expired=False):
        data=metadata((datetime.now(timezone.utc)-timedelta(days=3)).isoformat() if expired else None)
        data["profiles"] *= 2
        response=self.client.post("/transitability",data={"metadata":json.dumps(data)},files={"image":("scene.png",image_bytes(),"image/png")})
        self.assertEqual(response.status_code,200,response.text)
        return {"id":str(uuid4()),"profiles":[self.profile,self.profile],"result":response.json()}

    def save(self, payload):
        return self.client.post("/analyses",data={"metadata":json.dumps(payload)},files={"image":("scene.png",image_bytes(),"image/png")})

    def test_profiles_crud_and_isolation(self):
        for _ in range(2):
            response=self.client.post("/profiles",json=self.profile);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(self.fake.tables["profiles"]),1)
        self.assertEqual(len(self.client.get("/profiles").json()),1)
        changed={**self.profile,"name":"Updated"}
        self.assertEqual(self.client.put("/profiles/"+self.profile["id"],json=changed).json()["name"],"Updated")
        foreign={**self.profile,"id":str(uuid4()),"owner":"someone-else"}
        self.fake.tables["profiles"][foreign["id"]]=foreign
        self.assertEqual(len(self.client.get("/profiles").json()),1)
        self.assertEqual(self.client.delete("/profiles/"+self.profile["id"]).status_code,204)
        self.assertEqual(len(self.client.get("/profiles").json()),0)

    def test_all_routes_authenticate_before_reading_body(self):
        self.client.headers.pop("Authorization")
        for method,path in [("GET","/profiles"),("POST","/profiles"),("PUT","/profiles/"+str(uuid4())),("DELETE","/profiles/"+str(uuid4())),("GET","/analyses"),("GET","/analyses/"+str(uuid4())),("POST","/analyses"),("DELETE","/analyses/"+str(uuid4()))]:
            self.assertEqual(self.client.request(method,path,content=b"invalid-body").status_code,401)
        self.assertEqual(len(self.fake.requests),0)

    def test_analysis_private_files_snapshots_no_reinference(self):
        payload=self.analysis();self.assertEqual(self.save(payload).status_code,200)
        identifier=payload["id"];record=self.fake.tables["analyses"][identifier]
        self.assertIsNone(record["result"]["mask"])
        self.assertEqual(len(self.fake.objects),2)
        self.client.post("/profiles",json=self.profile)
        self.client.put("/profiles/"+self.profile["id"],json={**self.profile,"name":"Changed"})
        self.assertEqual(self.client.get("/analyses").json()[0]["id"],identifier)
        detail=self.client.get("/analyses/"+identifier).json()
        self.assertEqual(detail["profiles"][0]["name"],"Functional example")
        self.assertIn("token=",detail["image_url"]);self.assertIn("token=",detail["mask_url"])
        self.assertEqual(self.mock_vision.call_count,1)
        self.assertEqual(self.save(payload).status_code,200)
        self.assertEqual(len(self.fake.tables["analyses"]),1)
        self.assertEqual(self.client.delete("/analyses/"+identifier).status_code,204)
        self.assertFalse(self.fake.objects);self.assertFalse(self.fake.tables["analyses"])

    def test_expired_saved_without_invented_mask(self):
        payload=self.analysis(expired=True);self.assertEqual(self.save(payload).status_code,200)
        detail=self.client.get("/analyses/"+payload["id"]).json()
        self.assertIsNone(detail["mask_url"]);self.assertFalse(detail["result"]["features"])
        self.assertEqual(detail["result"]["assessments"][0]["classification"],"undetermined")
        self.assertEqual(len(self.fake.objects),1);self.mock_vision.assert_not_called()

    def test_failed_upload_retries_same_record_without_duplicates(self):
        payload=self.analysis();self.fake.fail_upload=True
        self.assertEqual(self.save(payload).status_code,503)
        self.assertEqual(self.client.get("/analyses").json(),[])
        self.fake.fail_upload=False;self.assertEqual(self.save(payload).status_code,200)
        self.assertEqual(len(self.fake.tables["analyses"]),1);self.assertEqual(len(self.fake.objects),2)
        self.assertEqual(self.mock_vision.call_count,1)
        altered={**payload,"profiles":[{**self.profile,"name":"Different"},self.profile]}
        self.assertEqual(self.save(altered).status_code,409)

    def test_failed_delete_keeps_retryable_record(self):
        payload=self.analysis();self.save(payload);self.fake.fail_delete=True
        path="/analyses/"+payload["id"]
        self.assertEqual(self.client.delete(path).status_code,503)
        self.assertEqual(self.client.get("/analyses").json()[0]["status"],"deleting")
        self.fake.fail_delete=False;self.assertEqual(self.client.delete(path).status_code,204)
        self.assertFalse(self.fake.objects);self.assertFalse(self.fake.tables["analyses"])

    def test_invalid_images_mask_and_profile_rejected(self):
        payload=self.analysis();payload["profiles"][0]={**self.profile,"requirements":{**self.profile["requirements"],"minimum_passage_width":"wide"}}
        self.assertEqual(self.save(payload).status_code,422)
        payload=self.analysis();payload["result"]["mask"]["data"]="invalid"
        self.assertEqual(self.save(payload).status_code,422)
        bad={**self.profile,"requirements":{**self.profile["requirements"],"accepts_detour":True}}
        self.assertEqual(self.client.post("/profiles",json=bad).status_code,422)

    def test_unconfigured_storage_fails_closed(self):
        self.client.app.state.storage=None
        self.assertEqual(self.client.get("/profiles").status_code,503)
        self.client.app.state.storage=self.store
