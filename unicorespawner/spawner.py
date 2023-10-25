import asyncio
import html
import json
import re
import time
from datetime import datetime

import pyunicore.client as pyunicore
from forwardbasespawner import ForwardBaseSpawner
from jupyterhub.utils import maybe_future
from jupyterhub.utils import url_escape_path
from jupyterhub.utils import url_path_join
from pyunicore.forwarder import Forwarder
from requests.exceptions import HTTPError
from traitlets import Any
from traitlets import Bool
from traitlets import Dict
from traitlets import Integer


class UnicoreSpawner(ForwardBaseSpawner):
    job_descriptions = Dict(
        config=True,
        help="""
        Multiple named job descriptions to start different UNICORE Jobs.
        
        If `Spawner.user_options["job"]` is defined, it will be used
        to get one of the defined jobs. Otherwise the job with key `default`
        will be used.
        
        Replacable variables can be added with angle brackets (chevrons) in
        the job_description. 
        UnicoreSpawner will replace these variables with their actual value.
        Replacable keys are:
         - any env variable
         - any user_option key
         - any key defined in Spawner.additional_replacements
        
        Has to be a dict or a callable, which returns a dict.
        More information about job_description:
        https://unicore-docs.readthedocs.io/en/latest/user-docs/rest-api/job-description/index.html
        
        Example::
        
        import os
        import json
        async def get_job_description(spawner):
            job = spawner.user_options.get("job", ["None"])
            if type(job) != list:
                job = [job]
            job = job[0]
            
            with open(f"/mnt/jobs/{job}/job_description.json", "r") as f:
                job_description = json.load(f)
            
            job_description["Imports"] = {}
            for subdir, dirs, files in os.walk("/mnt/jobs/{job}/input"):
                for file in files:
                    with open(os.path.join(subdir, file), "r") as f:
                        job_description["Imports"][file] = f.read()

            return job_description


        c.UnicoreSpawner.job_descriptions = {
            "job-1": get_job_description,
            "job-2": get_job_description
        }     
        """,
    )

    additional_replacements = Any(
        config=True,
        default_value={},
        help="""
        Define variables for each defined user_option key-value pair.
        This variables will be replaced in the job_description.
        
        With these replacements the same template job_description
        can be used for multiple systems and versions.
        
        In the example below all occurrences of `<startmsg>` or `<version>`
        in the job description will be replaced, depending on
        the defined user_options `system` and `job`. This reduces redundancy
        in `Spawner.job_descriptions` configuration (by using the same 
        function for multiple jobs) and in configuration files 
        (by using variables within the job description file).
        
        Example::
        
        {
            "system": {
                "local": {
                    "startmsg": "Starting job on local system"
                },
                "remote": {
                    "startmsg": "Starting job on remote system"
                }
            },
            "job": {
                "job-1": {
                    "version": "1.0.0"
                },
                "job-2": {
                    "version": "1.1.0"
                }
            }
        }
        """,
    )

    async def get_additional_replacements(self):
        """Get additional_replacements for job_description

        Returns:
          additional_replacements (dict): Used in Unicore Job description
        """

        if callable(self.additional_replacements):
            additional_replacements = await maybe_future(
                self.additional_replacements(self)
            )
        else:
            additional_replacements = self.additional_replacements
        return additional_replacements

    unicore_job_delete = Bool(
        config=True,
        default_value=True,
        help="""
        Whether unicore jobs should be deleted when stopped or not.
        """,
    )

    download_path = Any(
        config=True,
        default_value=False,
        help="""
        Function to define where to store stderr/stdout after stopping
        the job.
        
        String, False or Callable.
        
        Must return a string to the directory, where the output will be stored.
        False if nothing should be stored (default).
        Maybe a coroutine.
        
        """,
    )

    async def get_download_path(self):
        """Get additional_replacements for job_description

        Returns:
          additional_replacements (dict): Used in Unicore Job description
        """

        if callable(self.download_path):
            download_path = await maybe_future(self.download_path(self))
        else:
            download_path = self.download_path
        return download_path

    async def get_unicore_cert_path(self):
        """Get unicore cert path

        Returns:
          path (string or false): Used in Unicore communication
        """

        if callable(self.unicore_cert_path):
            unicore_cert_path = await maybe_future(self.unicore_cert_path(self))
        else:
            unicore_cert_path = self.unicore_cert_path
        return unicore_cert_path

    unicore_cert_path = Any(
        config=True,
        default_value=False,
        help="""
        UNICORE ca. Used in communication with Unicore.
        String, False or Callable
        
        Example::
        
        async def unicore_cert_path(spawner):
            if spawner.user_options["system"][0] == "abc":
                return "/mnt/certs/geant.crt"
        
        c.UnicoreSpawner.unicore_cert_path = unicore_cert_path
        """,
    )

    unicore_cert_url = Any(
        config=True,
        default_value=False,
        help="""
        Unicore certificate url. Used for verficiation with Unicore notifications.
        String or Callable
        default: f"{self.unicore_site_url}/certificate
        
        Example::
        
        async def unicore_cert_url(spawner):
            site_url = await spawner.get_unicore_site_url()
            return f"{site_url}/certificate"
        
        c.UnicoreSpawner.unicore_cert_url = unicore_cert_url
        """,
    )

    async def get_unicore_cert_url(self):
        """Get unicore cert url

        Returns:
          path (string): Used in verification with Unicore notification
        """

        if callable(self.unicore_cert_url):
            unicore_cert_url = await maybe_future(self.unicore_cert_url(self))
        elif self.unicore_cert_url:
            unicore_cert_url = self.unicore_cert_url
        else:
            site_url = await self.get_unicore_site_url()
            unicore_cert_url = f"{site_url.rstrip('/')}/certificate"
        return unicore_cert_url

    unicore_site_url = Any(
        config=True,
        help="""
        UNICORE site url.
        
        String or callable.
        Maybe a coroutine.
        
        Example::
        
        async def site_url(spawner):
            if spawner.user_options["system"][0] == "abc":
                return "https://abc.com:8080/DEMO-SITE/rest/core"
        
        c.UnicoreSpawner.unicore_site_url = site_url
        """,
    )

    async def get_unicore_site_url(self):
        """Get unicore site url

        Returns:
          url (string): Used in Unicore communication
        """

        if callable(self.unicore_site_url):
            url = await maybe_future(self.unicore_site_url(self))
        else:
            url = self.unicore_site_url
        return url

    unicore_internal_forwarding = Any(
        config=True,
        default_value=True,
        help="""
        Whether to use the unicore forwarding feature or an
        external solution. 
        See documentation for more information.
        
        Boolean or Callable.
        """,
    )

    async def get_unicore_internal_forwarding(self):
        if callable(self.unicore_internal_forwarding):
            unicore_internal_forwarding = await maybe_future(
                self.unicore_internal_forwarding(self)
            )
        else:
            unicore_internal_forwarding = self.unicore_internal_forwarding
        return unicore_internal_forwarding

    bss_notification_config = Any(
        config=True,
        default_value={
            "PENDING": {
                "progress": 33,
                "summary": "Your slurm job is currently in status PENDING.",
                "details": "Job is awaiting resource allocation.",
            },
            "CONFIGURING": {
                "progress": 35,
                "summary": "Your slurm job is currently in status CONFIGURING. This may take up to 7 minutes.",
                "details": "Job has been allocated resources, but are waiting for them to become ready for use (e.g. booting).",
            },
        },
        help="""
        Configure events shown to the user, when Unicore
        gives an bss status update to api_notifications handler.
        """,
    )

    async def get_bss_notification_config(self):
        if callable(self.bss_notification_config):
            bss_notification_config = await maybe_future(
                self.bss_notification_config(self)
            )
        else:
            bss_notification_config = self.bss_notification_config
        return bss_notification_config

    download_max_bytes = Integer(
        config=True,
        default_value=4096,
        help="""
        Unicore max_bytes for Download stderr and stdout
        """,
    )

    unicore_transport_kwargs = Any(
        config=True,
        default_value={},
        help="""
        kwargs used in pyunicore.Transport(**kwargs) call.
        Check https://github.com/HumanBrainProject/pyunicore for more
        information.
        
        Example::
        
        async def transport_kwargs(spawner):
            auth_state = await spawner.user.get_auth_state()
            return {
                "credential": auth_state["access_token"],
                "oidc": False,
                "verify": "/mnt/unicore/cert.crt",
                # "verify": False,
                "timeout": 30
            }
        
        c.UnicoreSpawner.unicore_transport_kwargs = transport_kwargs
        """,
    )

    async def get_unicore_transport_kwargs(self):
        """Get unicore transport kwargs

        Returns:
          kwargs (dict): Used in Unicore communication
        """

        if callable(self.unicore_transport_kwargs):
            kwargs = await maybe_future(self.unicore_transport_kwargs(self))
        else:
            kwargs = self.unicore_transport_kwargs
        return kwargs

    unicore_transport_preferences = Any(
        config=True,
        default_value=False,
        help="""
        Define preferences that should be set to transport object.

        Example::
        
        async def transport_preferences(spawner):
            account = spawner.user_options.get("account", None)
            if type(account) != list:
                account = [account]
            account = account[0]
            
            project = spawner.user_options.get("project", None)
            if type(project) != list:
                project = [project]
            project = project[0]
            
            return f"uid:{account},group:{project}"
        """,
    )

    async def get_unicore_transport_preferences(self):
        """Get unicore transport preferences

        Returns:
          preference (string): Used in Unicore communication
        """

        if callable(self.unicore_transport_preferences):
            preferences = await maybe_future(self.unicore_transport_preferences(self))
        else:
            preferences = self.unicore_transport_preferences
        return preferences

    def timed_func_call(self, func, *args, **kwargs):
        tic = time.time()
        try:
            ret = func(*args, **kwargs)
        finally:
            toc = time.time() - tic
            extra = {
                "tictoc": f"{func.__module__}.{func.__name__}",
                "duration": toc,
            }
            self.log.debug(
                f"{self._log_name} - UNICORE communication ( {toc}s )",
                extra=extra,
            )
        return ret

    async def _get_transport(self):
        transport_kwargs = await self.get_unicore_transport_kwargs()
        preferences = await self.get_unicore_transport_preferences()
        transport = self.timed_func_call(pyunicore.Transport, **transport_kwargs)

        if preferences:
            transport.preferences = preferences
        return transport

    async def _get_client(self):
        site_url = await self.get_unicore_site_url()
        transport = await self._get_transport()
        client = self.timed_func_call(pyunicore.Client, transport, site_url)
        return client

    async def _get_job(self):
        transport = await self._get_transport()
        job = self.timed_func_call(pyunicore.Job, transport, self.resource_url)
        return job

    def short_logs(self, log_list, lines):
        if type(log_list) == str:
            log_list = log_list.split("\n")
        log_list = [x.split("\n") for x in log_list]
        log_list_clear = []
        for l in log_list:
            if type(l) == list:
                log_list_clear.extend(l)
            else:
                log_list_clear.append(l)
        if lines > 0:
            log_list_clear = log_list_clear[-lines:]
        if lines < len(log_list_clear):
            log_list_clear.insert(0, "...")
        return log_list_clear

    def _prettify_error_logs(self, log_list, lines, summary):
        log_list_short = self.short_logs(log_list, lines)
        log_list_short_escaped = list(map(lambda x: html.escape(x), log_list_short))
        logs_s = "<br>".join(log_list_short_escaped)
        return f"<details><summary>&nbsp&nbsp&nbsp&nbsp{summary}(click here to expand):</summary>{logs_s}</details>"

    def download_file(self, job, file):
        file_path = job.working_dir.stat(file)
        file_size = file_path.properties["size"]
        if file_size == 0:
            return f"{file} is empty"
        offset = max(0, file_size - self.download_max_bytes)
        s = file_path.raw(offset=offset)
        return s.data.decode()

    async def unicore_stop_event(self, spawner):
        job = await self._get_job()

        unicore_stderr = self.download_file(job, "stderr")
        unicore_stdout = self.download_file(job, "stdout")
        now = datetime.now().strftime("%Y_%m_%d %H:%M:%S.%f")[:-3]

        summary = f"UNICORE Job stopped with exitCode: {job.properties.get('exitCode', 'unknown exitCode')}"

        unicore_status_message = job.properties.get(
            "statusMessage", "unknown statusMessage"
        )
        unicore_logs_details = self._prettify_error_logs(
            job.properties.get("log", []), 20, "UNICORE logs"
        )

        unicore_stdout_details = self._prettify_error_logs(
            unicore_stdout,
            20,
            "Job stdout",
        )
        unicore_stderr_details = self._prettify_error_logs(
            unicore_stderr,
            20,
            "Job stderr",
        )

        details = "".join(
            [
                unicore_status_message,
                unicore_logs_details,
                unicore_stdout_details,
                unicore_stderr_details,
            ]
        )
        event = {
            "failed": True,
            "progress": 100,
            "html_message": f"<details><summary>{now}: {summary}</summary>{details}</details>",
        }

        return event

    def get_string(self, value):
        if type(value) != list:
            value = [value]
        if len(value) == 0:
            return ""
        else:
            return str(value[0])

    def clear_state(self):
        super().clear_state()
        self.resource_url = ""

    def get_state(self):
        state = super().get_state()
        state["resource_url"] = self.resource_url
        return state

    def load_state(self, state):
        super().load_state(state)
        if "resource_url" in state:
            self.resource_url = state["resource_url"]

    def get_env(self):
        env = super().get_env()
        env["JUPYTERHUB_API_URL"] = self.get_public_api_url().rstrip()

        env[
            "JUPYTERHUB_ACTIVITY_URL"
        ] = f"{env['JUPYTERHUB_API_URL']}/users/{self.user.name}/activity"

        # Add URL to receive UNICORE status updates
        url_parts = ["users", "progress", "updateunicore", self.user.escaped_name]
        if self.name:
            url_parts.append(self.name)
        env[
            "JUPYTERHUB_UNICORE_NOTIFICATION_URL"
        ] = f"{env['JUPYTERHUB_API_URL']}/{url_path_join(*url_parts)}"
        return env

    async def _start(self):
        job = self.get_string(self.user_options.get("job", ["default"]))
        job_description = self.job_descriptions[job]

        if callable(job_description):
            job_description = await maybe_future(job_description(self))

        env = self.get_env()
        job_description = json.dumps(job_description)
        for key, value in self.user_options.items():
            job_description = job_description.replace(
                f"<{key}>", self.get_string(value).replace('"', '\\"')
            )
        for key, value in env.items():
            if type(value) == int:
                job_description = job_description.replace(
                    f"<{key}>", str(value).replace('"', '\\"')
                )
            else:
                job_description = job_description.replace(
                    f"<{key}>", value.replace('"', '\\"')
                )

        additional_replacements = await self.get_additional_replacements()
        for ukey, _uvalue in self.user_options.items():
            uvalue = self.get_string(_uvalue)
            for key, value in (
                additional_replacements.get(ukey, {}).get(uvalue, {}).items()
            ):
                job_description = job_description.replace(f"<{key}>", value)
        job_description = json.loads(job_description)

        jd_env = job_description.get("Environment", {}).copy()

        # Remove keys that might disturb new JupyterLabs (like PATH, PYTHONPATH)
        for key in set(env.keys()):
            if not (key.startswith("JUPYTER_") or key.startswith("JUPYTERHUB_")):
                self.log.debug(f"{self._log_name} - Remove {key} from env")
                del env[key]
        jd_env.update(env)
        job_description["Environment"] = jd_env

        client = await self._get_client()
        unicore_job = self.timed_func_call(client.new_job, job_description)
        self.resource_url = unicore_job.resource_url

        unicore_forwarding = await self.get_unicore_internal_forwarding()
        if unicore_forwarding:
            await self.run_ssh_forward()
            return f"http://{self.svc_name}:{self.port}"
        else:
            return ""

    async def ssh_default_forward(self):
        unicore_forwarding = await self.get_unicore_internal_forwarding()
        if unicore_forwarding:
            unicore_job = await self._get_job()
            while unicore_job.is_running():
                if unicore_job.properties.get("status", "") != "RUNNING":
                    self.log.debug(f"{self._log_name} - Wait for JupyterLab ...")
                    await asyncio.sleep(5)
                    continue
                # Download stderr to receive port + address
                unicore_stderr = self.download_file(unicore_job, "stderr")
                if type(unicore_stderr) == str:
                    unicore_stderr = unicore_stderr.split("\n")
                log_line = [
                    x
                    for x in unicore_stderr
                    if f"/user/{self.user.escaped_name}/{url_escape_path(self.name)}/"
                    in x
                ]
                if log_line:
                    log_line = log_line[0]
                    result = re.search("(http|https)://([^:]+):([^/]+)", log_line)
                    address = result.group(2)
                    port = result.group(3)

                    loop = asyncio.get_running_loop()

                    def run_forward():
                        while unicore_job.is_running():
                            try:
                                endpoint = unicore_job.links["forwarding"]
                                tr = unicore_job.transport._clone()
                                tr.use_security_sessions = False
                                self.forwarder = Forwarder(
                                    tr,
                                    endpoint,
                                    service_port=int(port),
                                    service_host=address,
                                    debug=True,
                                )
                                self.forwarder.run(self.port)
                            except:
                                self.log.exception(
                                    f"{self._log_name} - Could not start unicore forward"
                                )
                                time.sleep(2)

                    self.unicore_forwarder = loop.run_in_executor(None, run_forward)
                    self.log.info(
                        f"{self._log_name} - Unicore Forwarding created - {self.port}:{address}:{port}"
                    )
                    break
                await asyncio.sleep(2)
        else:
            return await super().ssh_default_forward()

    async def ssh_default_forward_remove(self):
        unicore_forwarding = await self.get_unicore_internal_forwarding()
        if unicore_forwarding:
            unicore_forwarder = getattr(self, "unicore_forwarder", None)
            if unicore_forwarder:
                try:
                    unicore_forwarder.cancel()
                    await maybe_future(unicore_forwarder)
                except asyncio.CancelledError:
                    pass
            forwarder = getattr(self, "forwarder", None)
            if forwarder:
                forwarder.stop_forwarding()
        else:
            return await super().ssh_default_forward_remove()

    async def _poll(self):
        if not self.resource_url:
            return 0

        job = await self._get_job()
        try:
            is_running = self.timed_func_call(job.is_running)
            self.log.debug(
                f"{self._log_name} - Poll is running: {is_running} for {self.resource_url}"
            )
        except HTTPError as e:
            if getattr(e.response, "status_code", 500) == 404:
                self.log.info(
                    f"{self._log_name} - Resource URL {self.resource_url} not found ({e.response.status_code})"
                )
                return 0
            self.log.exception(
                f"{self._log_name} - Could not receive job status. Keep running"
            )
            return None
        except:
            self.log.exception(
                f"{self._log_name} - Could not receive job status. Keep running"
            )
            return None

        if is_running:
            return None
        else:
            return 0

    async def _stop(self, now, **kwargs):
        if not self.resource_url:
            return

        job = await self._get_job()

        unicore_stdout = self.download_file(job, "stdout")
        unicore_stderr = self.download_file(job, "stderr")
        unicore_logs = job.properties.get("log", [])
        self.log.info(
            f"{self._log_name} - Stop job. unicore log:\n{self.short_logs(unicore_logs, 20)}"
        )
        self.log.info(
            f"{self._log_name} - Stop job. stdout:\n{self.short_logs(unicore_stdout, 20)}"
        )
        self.log.info(
            f"{self._log_name} - Stop job. stderr:\n{self.short_logs(unicore_stderr, 20)}"
        )
        job.abort()

        if self.unicore_job_delete:
            job.delete()
