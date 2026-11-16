# UNICORESpawner

Also look at the configuration of the base class [JupyterHub ForwardBaseSpawner](https://jupyterhub-forwardbasespawner.readthedocs.io/en/latest/spawners/forwardbasespawner.html).

`UnicoreSpawner` is a subclass of the [ForwardBaseSpawner](https://github.com/kreuzert/jupyterhub-forwardbasespawner). All options of the `ForwardBaseSpawner` and of JupyterHub's `Spawner` can be used in addition (e.g. `ssh_key`, `ssh_node`, `public_api_url`, `svc_name_template`, `dns_name_template`, `http_timeout`, `options_form`). The options specific to the `UnicoreSpawner` are documented below.

## `job_description`

Type: `dict` or `callable` (may be a coroutine)

Multiple named job descriptions to start different UNICORE Jobs.

If `Spawner.user_options["job"]` is defined, it will be used to get one of the defined jobs. Otherwise the job with key `default` will be used.

Replacable variables can be added with angle brackets (chevrons) in the job_description. UnicoreSpawner will replace these variables with their actual value. Replacable keys are:

- any env variable
- any user_option key
- any key defined in `Spawner.additional_replacements`

More information about job_description: [UNICORE job description](https://unicore-docs.readthedocs.io/en/latest/user-docs/rest-api/job-description/index.html).

```python
import os
import json

async def get_job_description(spawner, user_options):
    job = user_options["job"]
    with open(f"/mnt/jobs/{job}/job_description.json", "r") as f:
        job_description = json.load(f)

    job_description["Imports"] = {}
    for subdir, dirs, files in os.walk(f"/mnt/jobs/{job}/input"):
        for file in files:
            with open(os.path.join(subdir, file), "r") as f:
                job_description["Imports"][file] = f.read()

    return job_description

c.UnicoreSpawner.job_description = get_job_description
```

## `additional_replacements`

Type: `dict` or `callable`, default `{}`

Define variables for each defined user_option key-value pair. These variables will be replaced in the job_description.

With these replacements the same template job_description can be used for multiple systems and versions.

In the example below all occurrences of `<startmsg>` or `<version>` in the job description will be replaced, depending on the defined user_options `system` and `job`. This reduces redundancy in `Spawner.job_descriptions` configuration (by using the same function for multiple jobs) and in configuration files (by using variables within the job description file).

```json
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
```

## `unicore_site_url`

Type: `str` or `callable` (may be a coroutine)

UNICORE site url.

```python
async def site_url(spawner):
    if spawner.user_options["system"][0] == "abc":
        return "https://abc.com:8080/DEMO-SITE/rest/core"

c.UnicoreSpawner.unicore_site_url = site_url
```

## `unicore_transport_kwargs`

Type: `dict` or `callable` (may be a coroutine), default `{}`

kwargs used in the `pyunicore.Transport(**kwargs)` call. Check [pyunicore](https://github.com/HumanBrainProject/pyunicore) for more information.

```python
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
```

## `unicore_transport_preferences`

Type: `str` or `callable` (may be a coroutine), default `False`

Define preferences that should be set to the transport object.

```python
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
```

## `unicore_cert_path`

Type: `str` or `callable` (may be a coroutine), default `False`

UNICORE CA. Used in communication with UNICORE.

```python
async def unicore_cert_path(spawner):
    if spawner.user_options["system"][0] == "abc":
        return "/mnt/certs/geant.crt"

c.UnicoreSpawner.unicore_cert_path = unicore_cert_path
```

## `unicore_cert_url`

Type: `str` or `callable` (may be a coroutine), default `False`

UNICORE certificate url. Used for verification with UNICORE notifications.
If not set, `f"{unicore_site_url}/certificate"` is used.

```python
async def unicore_cert_url(spawner):
    site_url = await spawner.get_unicore_site_url()
    return f"{site_url}/certificate"

c.UnicoreSpawner.unicore_cert_url = unicore_cert_url
```

## `unicore_internal_forwarding`

Type: `bool` or `callable`, default `True`

Whether to use the UNICORE forwarding feature or an external solution.

## `unicore_job_delete`

Type: `bool`, default `True`

Whether UNICORE jobs should be deleted when stopped or not.

## `download_path`

Type: `str` or `callable` (may be a coroutine), default `False`

Function to define where to store stderr/stdout after stopping the job.

Must return a string to the directory, where the output will be stored. `False` if nothing should be stored (default).

## `download_max_bytes`

Type: `int`, default `4096`

UNICORE max_bytes for downloading stderr and stdout.

## `store_environment_in_file`

Type: `bool`, default `False`

Store all environment variables in a `.env` file, instead of storing them in the job_description directly. Might be useful to hide them from other users.

## `bss_notification_config`

Type: `dict` or `callable`, default:

```json
{
    "PENDING": {
        "progress": 33,
        "summary": "Your slurm job is currently in status PENDING.",
        "details": "Job is awaiting resource allocation."
    },
    "CONFIGURING": {
        "progress": 35,
        "summary": "Your slurm job is currently in status CONFIGURING. This may take up to 7 minutes.",
        "details": "Job has been allocated resources, but are waiting for them to become ready for use (e.g. booting)."
    }
}
```

Configure events shown to the user, when UNICORE gives a bss status update to the `api_notifications` handler.
