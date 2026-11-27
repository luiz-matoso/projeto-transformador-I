import copy
import json
import unittest
from dataclasses import asdict
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from ml.functional_profile import functional_requirements, functional_spec, COMPLEMENTARY
from api.schemas.workspace import ProfileWrite


def answers(**updates):
    return {"schema_version":1,"wheelchair_type":"manual","assistance":"none",
            "narrow_spaces":"without_difficulty","uneven_surfaces":"without_difficulty",
            "small_level_changes":"with_difficulty","steps":"unable","tight_maneuvers":"with_difficulty",
            "obstacle_avoidance":"without_difficulty","requires_ramps":True,
            "inclines":"unable","accepts_detours":True,**updates}


class FunctionalTranslationTests(unittest.TestCase):
    def test_width_surface_and_obstacles_are_explicit(self):
        for ability,width,surface,obstruction in [("without_difficulty","narrow","major_problems",True),("with_difficulty","adequate","minor_problems",True),("unable","wide","regular_only",False)]:
            p=functional_requirements(answers(narrow_spaces=ability,uneven_surfaces=ability,obstacle_avoidance=ability))
            self.assertEqual((p.minimum_passage_width,p.surface_tolerance,p.accepts_partial_obstruction),(width,surface,obstruction))
    def test_levels_and_conflicting_answers(self):
        self.assertEqual(functional_requirements(answers(small_level_changes="unable")).level_change_tolerance,"none")
        self.assertEqual(functional_requirements(answers()).level_change_tolerance,"minor")
        self.assertEqual(functional_requirements(answers(steps="with_difficulty")).level_change_tolerance,"step")
        with self.assertRaises(ValueError):functional_requirements(answers(small_level_changes="unable",steps="without_difficulty"))
    def test_identification_does_not_infer_abilities(self):
        self.assertEqual(functional_requirements(answers()),functional_requirements(answers(wheelchair_type="powered",assistance="constant")))
    def test_complementary_needs_are_not_silently_used(self):
        self.assertEqual(functional_requirements(answers()),functional_requirements(answers(tight_maneuvers="unable",requires_ramps=False,inclines="without_difficulty",accepts_detours=False)))
        self.assertEqual(set(COMPLEMENTARY),{"tight_maneuvers","requires_ramps","inclines","accepts_detours"})
        self.assertTrue(functional_spec()["notes"])
    def test_incomplete_profile_and_mismatched_requirements_rejected(self):
        a=answers();a.pop("assistance")
        with self.assertRaises(ValueError):functional_requirements(a)
        with self.assertRaises(ValueError):ProfileWrite(id=uuid4(),name="Example",functional=answers(),requirements={**asdict(functional_requirements(answers())),"minimum_passage_width":"wide"})
    def test_legacy_has_no_invented_answers(self):
        old=ProfileWrite(id=uuid4(),name="Previous",requirements=asdict(functional_requirements(answers())))
        self.assertIsNone(old.functional)
        self.assertNotIn("functional",old.model_dump(exclude_none=True))


class FunctionalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        from tests.test_workspace_api import WorkspaceTests
        self.fixture=WorkspaceTests("runTest");self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.client=self.fixture.client
    def profile(self,**changes):
        return {"id":str(uuid4()),"name":"Functional "+str(uuid4()),"functional":answers(**changes)}
    def test_create_edit_and_read_preserve_answers(self):
        p=self.profile();response=self.client.post("/profiles",json=p);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["functional"],p["functional"])
        self.assertEqual(response.json()["requirements"]["minimum_passage_width"],"narrow")
        p["functional"]["narrow_spaces"]="unable"
        edited=self.client.put("/profiles/"+p["id"],json=p);self.assertEqual(edited.status_code,200,edited.text)
        self.assertEqual(edited.json()["requirements"]["minimum_passage_width"],"wide")
        self.assertEqual(self.client.get("/profiles").json()[0]["functional"],p["functional"])
    def test_functional_inference_and_immutable_history_snapshots(self):
        p,q=self.profile(),self.profile(narrow_spaces="unable")
        data={"profiles":[{"functional":v["functional"]} for v in (p,q)],"observation":{"source":"controlled test","observed_at":datetime.now(timezone.utc).isoformat()}}
        from tests.test_api import image_bytes
        result=self.client.post("/transitability",data={"metadata":json.dumps(data)},files={"image":("x.png",image_bytes(),"image/png")})
        self.assertEqual(result.status_code,200,result.text);result=result.json()
        self.assertEqual([r["classification"] for r in result["assessments"]],["transitable","non_transitable"])
        self.assertEqual(result["assessments"][0]["unassessed_functional_needs"],list(COMPLEMENTARY))
        self.assertEqual(self.fixture.mock_vision.call_count,1)
        payload={"id":str(uuid4()),"profiles":[p,q],"result":result}
        self.assertEqual(self.fixture.save(payload).status_code,200)
        for item in (p,q):self.client.post("/profiles",json=item)
        old=copy.deepcopy(p["functional"]);p["functional"]["uneven_surfaces"]="unable"
        self.assertEqual(self.client.put("/profiles/"+p["id"],json=p).status_code,200)
        historical=self.client.get("/analyses/"+payload["id"]).json()
        self.assertEqual(historical["profiles"][0]["functional"],old)
        self.assertEqual(self.fixture.mock_vision.call_count,1)
        payload["profiles"][0]["functional"]["uneven_surfaces"]="unable"
        self.assertEqual(self.fixture.save(payload).status_code,422)
    def test_legacy_client_cannot_silently_discard_new_answers(self):
        p=self.profile();response=self.client.post("/profiles",json=p);self.assertEqual(response.status_code,200)
        old_client={"id":p["id"],"name":"Renamed","requirements":response.json()["requirements"]}
        renamed=self.client.put("/profiles/"+p["id"],json=old_client);self.assertEqual(renamed.status_code,200,renamed.text)
        self.assertEqual(renamed.json()["functional"],p["functional"])
        old_client["requirements"]["minimum_passage_width"]="wide"
        self.assertEqual(self.client.put("/profiles/"+p["id"],json=old_client).status_code,409)
        self.assertEqual(self.client.get("/profiles").json()[0]["functional"],p["functional"])

    def test_expired_functional_profile_never_runs_perception(self):
        from tests.test_api import image_bytes
        data={"profiles":[{"functional":answers()}],"observation":{"source":"simulated expired","observed_at":(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}}
        response=self.client.post("/transitability",data={"metadata":json.dumps(data)},files={"image":("x.png",image_bytes(),"image/png")})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["assessments"][0]["classification"],"undetermined")
        self.assertEqual(response.json()["assessments"][0]["reasons"][0]["code"],"observation_expired")
        self.fixture.mock_vision.assert_not_called()

if __name__=="__main__":unittest.main()
