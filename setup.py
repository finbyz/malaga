from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in malaga/__init__.py
from malaga import __version__ as version

setup(
	name="malaga",
	version=version,
	description="malaga",
	author="nandu bhadada",
	author_email="nandu@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
