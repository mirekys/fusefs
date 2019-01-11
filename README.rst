# fusefs

Python FUSE module for mounting all filesystems supported by the
[PyFilesystem2](https://github.com/PyFilesystem/pyfilesystem2) module.

NOTE: Currently it supports just Read/Only mounts of ZIP/TAR archives.

# Instaling

* Install ```fuse``` and ```fuse-devel``` system packages
* Build & Install fusefs with poetry:
```python
pip install poetry
git clone https://github.com/mirekys/fusefs.git
cd fusefs
poetry build
cd dist
tar -xvf fusefs-0.1.0.tar.gz
pip install -e fusefs-0.1.0/
```

# Usage
```
fusefs <source> <mountpoint>
```

Where ```source``` must be in [PyFilesystem2 format](https://docs.pyfilesystem.org/en/latest/openers.html)