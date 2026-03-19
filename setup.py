from setuptools import find_packages, setup


setup(
    name="multi-tenant-webinar-demo",
    version="0.1.0",
    packages=find_packages(include=["shared", "shared.*", "tenant_*", "tenant_*.*", "tests"]),
)

