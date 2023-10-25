import datetime
import inspect
import json

import jwt
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate
from jupyterhub.apihandlers import default_handlers
from jupyterhub.apihandlers.base import APIHandler


class SpawnEventsUnicoreAPIHandler(APIHandler):
    def check_xsrf_cookie(self):
        pass

    async def post(self, user_name, server_name=""):
        user = self.find_user(user_name)
        if user is None:
            self.set_status(404)
            return
        if server_name not in user.spawners:
            self.set_status(404)
            return

        spawner = user.spawners[server_name]
        cert_path = await spawner.get_unicore_cert_path()
        cert_url = await spawner.get_unicore_cert_url()

        with requests.get(
            cert_url, headers={"accept": "text/plain"}, verify=cert_path
        ) as r:
            r.raise_for_status()
            cert = r.content

        # Validate certifica
        cert_obj = load_pem_x509_certificate(cert, default_backend())
        token = self.request.headers.get("Authorization", "Bearer -").split()[1]
        jwt.decode(token, cert_obj.public_key(), algorithms=["RS256"])

        body = self.request.body.decode("utf8")
        body = json.loads(body) if body else {}
        self.log.info(
            f"{spawner._log_name} - Unicore Status Update received - {body.get('status', '')}",
            extra={
                "uuidcode": spawner.name,
                "username": user.name,
                "userid": user.id,
                "action": "unicoreupdate",
                "body": body,
            },
        )
        if body.get("status", "") in ["FAILED", "SUCCESSFUL", "DONE"]:
            # spawner.poll will check the current status via UnicoreMgr.
            # This will download the logs and show them to the user.
            # It will also cancel the current spawn attempt.
            self.log.debug(
                f"{spawner._log_name} - Cancel spawner",
                extra={
                    "uuidcode": spawner.name,
                    "username": user.name,
                    "userid": user.id,
                },
            )
            if bool(spawner._spawn_pending or spawner.ready):
                try:
                    if not getattr(spawner, "resource_url", None):
                        spawner.resource_url = body.get("href", "")
                    event = await spawner.unicore_stop_event(spawner)
                except:
                    self.log.exception(
                        f"{spawner._log_name} - Could not create stop event"
                    )
                    event = None
                stop = spawner.stop(cancel=True, event=event)
                if inspect.isawaitable(stop):
                    await stop
        else:
            bssStatus = body.get("bssStatus", "")
            # It's in Running (UNICORE wise) state. We can now check for bssStatus to get more details
            bss_config = await spawner.get_bss_notification_config()
            for key, bssDetails in bss_config.items():
                if key == bssStatus:
                    now = datetime.datetime.now().strftime("%Y_%m_%d %H:%M:%S.%f")[:-3]
                    summary = bssDetails.get("summary", f"Slurm status: {key}")
                    details = bssDetails.get(
                        "details",
                        "You'll receive more information, when your slurm job proceeds.",
                    )
                    progress = int(bssDetails.get("progress", 35))
                    event = {
                        "failed": False,
                        "progress": progress,
                        "html_message": f"<details><summary>{now}: {summary}</summary>{details}</details>",
                    }
                    spawner.latest_events.append(event)

        self.set_status(200)


default_handlers.append(
    (r"/api/users/progress/updateunicore/([^/]+)", SpawnEventsUnicoreAPIHandler)
)
default_handlers.append(
    (r"/api/users/progress/updateunicore/([^/]+)/([^/]+)", SpawnEventsUnicoreAPIHandler)
)
