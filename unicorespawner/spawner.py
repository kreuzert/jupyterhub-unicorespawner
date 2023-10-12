import copy
import json
import time

import pyunicore.client as pyunicore
from forwardbasespawner import ForwardBaseSpawner
from jupyterhub.spawner import Spawner
from jupyterhub.utils import maybe_future
from jupyterhub.utils import url_path_join
from requests.exceptions import HTTPError
from traitlets import Any
from traitlets import Bool
from traitlets import Dict
from traitlets import Integer
from traitlets import Unicode


class UnicoreSpawner(Spawner):
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
        
        In the example below all occurrences of `{{startmsg}}` or `{{version}}`
        in the job description will be replaced, depending on
        the defined user_options `system` and `job`. This reduces redundancy
        in `Spawner.jobs` configuration (by using the same function for multiple
        jobs) and in configuration files (by using variables within the
        job description file).
        
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
        Whether unicore jobs should be deleted when stopped
        """,
    )

    download_path = Any(
        config=True,
        default_value="",
        help="""
        Function to define where to store stderr/stdout after stopping
        the job
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

    unicore_site_url = Any(
        config=True,
        help="""
        UNICORE site url.
        
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

    unicore_cert_path = Any(
        config=True,
        default_value=False,
        help="""
        UNICORE site certificate path. String or False
        """,
    )

    download_max_bytes = Integer(
        config=True,
        default_value=4096,
        help="""
        UNICORE max_bytes for Download stderr and stdout
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

    def get_string(self, value):
        if type(value) != list:
            value = [value]
        if len(value) == 0:
            return ""
        else:
            return str(value[0])

    def timed_func_call(self, func, *args, **kwargs):
        tic = time.time()
        try:
            ret = func(*args, **kwargs)
        finally:
            toc = time.time() - tic
            extra = {"tictoc": f"{func.__module__},{func.__name__}", "duration": toc}
            self.log.debug(
                f"{self._log_name} - UNICORE communication",
                extra=extra,
            )
        return ret

    async def _get_transport(self):
        transport_kwargs = await self.get_unicore_transport_kwargs()
        transport = self.timed_func_call(pyunicore.Transport, **transport_kwargs)
        preferences = await self.get_unicore_transport_preferences()
        if preferences:
            transport.preferences = preferences
        return transport

    async def _get_client(self):
        transport = await self._get_transport()
        url = await self.get_unicore_site_url()
        client = self.timed_func_call(pyunicore.Client, transport, url)
        return client

    async def _get_job(self):
        transport = await self._get_transport()
        job = self.timed_func_call(pyunicore.Job, transport, self.resource_url)
        return job

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
        if self.public_api_url:
            env["JUPYTERHUB_API_URL"] = self.public_api_url

        env[
            "JUPYTERHUB_ACTIVITY_URL"
        ] = f"{env['JUPYTERHUB_API_URL'].rstrip('/')}/users/{self.user.name}/activity"
        return env

    def start(self):
        return super().start()

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

        # UNICORE/X supports port-forwarding for batch jobs, but not
        # interactive jobs yet.
        # Until it supports it for all jobs, we rely on the base class
        # to create a port-forward process and add the correct return value.
        # --
        # if job_description.get("Job Type", "batch") in ["batch", "normal"]:
        #     from pyunicore.forwarder import open_tunnel
        #     sock = open_tunnel(unicore_job, self.port)
        #     return ("localhost", sock.getsockname()[1])

        return ""

    async def poll(self):
        return await super().poll()

    async def _poll(self):
        if not self.resource_url:
            return 0

        job = await self._get_job()
        try:
            is_running = self.timed_func_call(job.is_running)
            self.log.info(
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

    def download_file(self, job, file):
        file_path = job.working_dir.stat(file)
        file_size = file_path.properties["size"]
        if file_size == 0:
            return f"{file} is empty"
        offset = max(0, file_size - self.download_max_bytes)
        s = file_path.raw(offset=offset)
        return s.data.decode()

    async def stop(self, now, **kwargs):
        return await super().stop(now, **kwargs)

    async def _stop(self, now, **kwargs):
        if not self.resource_url:
            return

        job = await self._get_job()
        job.abort()
        stderr = self.download_file(job, "stderr")
        stdout = self.download_file(job, "stdout")
        self.log.info(f"{self._log_name} - Stop stderr:\n{stderr}")
        self.log.info(f"{self._log_name} - Stop stdout:\n{stdout}")
        if self.unicore_job_delete:
            job.delete()


class UnicoreForwardSpawner(UnicoreSpawner, ForwardBaseSpawner):
    async def start(self):
        return await ForwardBaseSpawner.start(self)

    async def poll(self):
        return await ForwardBaseSpawner.poll(self)

    async def stop(self, now=False, **kwargs):
        return await ForwardBaseSpawner.stop(self, now=now, **kwargs)
