
[![Documentation Status](https://readthedocs.org/projects/jupyterhub-unicorespawner/badge/?version=latest)](https://jupyterhub-unicorespawner.readthedocs.io/en/latest/?badge=latest)

# UNICORESpawner

The UNICORESpawner enables JupyterHub to spawn services via [UNICORE](https://www.unicore.eu).
It is a subclass of the [JupyterHub ForwardBaseSpawner](https://github.com/kreuzert/jupyterhub-forwardbasespawner).

## Features

UNICORESpawner combines the power of UNICORE with the simplicity of JupyterHub. Using the UNICORE REST-API, the UNICORESpawner can spawn services on any remote system connected to UNICORE/X. 
  
- Start jupyter notebook servers on hpc systems.
- Communication with jupyter server in a browser, even if they're running on batch nodes without internet access, enables "Supercomputing in a browser".
- Use Callback feature of UNICORE reduces poll overload. JupyterHub will be informed, if the stauts of the UNICORE job changes.
  
