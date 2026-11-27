"""Explicit test-only HTTP double for Supabase; never imported by production API."""
import json
from datetime import datetime, timezone
import httpx

class SupabaseFake:
    def __init__(self):
        self.tables = {"profiles": {}, "analyses": {}}
        self.objects = {}
        self.requests = []
        self.fail_upload = False
        self.fail_delete = False

    def __call__(self, request):
        self.requests.append(request)
        path, method = request.url.path, request.method
        data = json.loads(request.content) if request.content and "json" in request.headers.get("content-type", "") else None
        if path.startswith("/rest/v1/"):
            table = self.tables[path.rsplit("/", 1)[-1]]
            rows = list(table.values())
            for key in ("owner", "id"):
                if request.url.params.get(key):
                    rows = [r for r in rows if r[key] == request.url.params[key][3:]]
            if method == "POST":
                if data["id"] in table:
                    return httpx.Response(200, json=[])
                if path.endswith("/profiles") and any(row["owner"]==data["owner"] and row["name"].lower()==data["name"].lower() for row in table.values()):
                    return httpx.Response(409,json={"error":"duplicate name"})
                data = {"created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(), **data}
                table[data["id"]] = data
                return httpx.Response(201, json=[data])
            if method == "PATCH":
                for row in rows:
                    row.update(data)
                return httpx.Response(200, json=rows)
            if method == "DELETE":
                for row in rows:
                    table.pop(row["id"])
                return httpx.Response(204)
            if request.url.params.get("status"):
                rows = [r for r in rows if r["status"] in ("complete", "deleting")]
                rows.sort(key=lambda r: r["created_at"], reverse=True)
            offset = int(request.url.params.get("offset", "0"))
            limit = int(request.url.params.get("limit", "100000"))
            return httpx.Response(200, json=rows[offset:offset+limit])
        if path.startswith("/storage/v1/object/sign/"):
            key = path.removeprefix("/storage/v1/object/sign/")
            return httpx.Response(200, json={"signedURL": "/object/authenticated/" + key + "?token=test-only"})
        if path.startswith("/storage/v1/object/authenticated/"):
            key = path.removeprefix("/storage/v1/object/authenticated/")
            content, mime = self.objects[key]
            return httpx.Response(200, content=content, headers={"content-type": mime})
        if method == "POST":
            if self.fail_upload:
                return httpx.Response(503, json={"error": "test upload failure"})
            self.objects[path.removeprefix("/storage/v1/object/")] = (request.content, request.headers["content-type"])
            return httpx.Response(200, json={"Key": path})
        if method == "DELETE":
            if self.fail_delete:
                return httpx.Response(503, json={"error": "test delete failure"})
            bucket = path.rsplit("/", 1)[-1]
            for prefix in data["prefixes"]:
                self.objects.pop(bucket + "/" + prefix, None)
            return httpx.Response(200, json=[])
        return httpx.Response(404)
