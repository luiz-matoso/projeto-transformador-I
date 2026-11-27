import asyncio
import os
import secrets
import unittest
from uuid import uuid4
from api.schemas.workspace import ProfileWrite
from api.storage import WorkspaceStorage

@unittest.skipUnless(os.getenv("MOBILIZA_RUN_SUPABASE_TEST")=="1", "Supabase real requer opt-in e configuração local")
class RealSupabaseTests(unittest.TestCase):
    def test_profile_roundtrip_private_storage_and_database(self):
        async def check():
            store=WorkspaceStorage.from_env()
            self.assertIsNotNone(store,"Configure SUPABASE_URL e SUPABASE_SECRET_KEY")
            owner="integration-check-"+secrets.token_hex(8)
            profile=ProfileWrite(id=uuid4(),name="Integration check",requirements={"minimum_passage_width":"adequate","surface_tolerance":"minor_problems","level_change_tolerance":"minor","accepts_partial_obstruction":True})
            try:
                created=await store.save_profile(owner,profile)
                self.assertEqual(created["name"],profile.name)
                self.assertEqual(len(await store.profiles(owner)),1)
                await store.save_profile(owner,profile)
                self.assertEqual(len(await store.profiles(owner)),1)
                profile.name="Integration check edited"
                self.assertEqual((await store.save_profile(owner,profile,True))["name"],profile.name)
                buckets=await store.call("GET","/storage/v1/bucket")
                bucket=next(b for b in buckets if b["id"]==store.bucket)
                self.assertIs(bucket["public"],False)
            finally:
                await store.delete_profile(owner,str(profile.id))
                await store.close()
        asyncio.run(check())
