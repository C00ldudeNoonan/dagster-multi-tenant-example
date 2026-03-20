from setuptools import find_packages, setup


setup(
    name="multi-tenant-webinar-demo",
    version="0.1.0",
    packages=find_packages(
        include=[
            "shared",
            "shared.*",
            "harbor_outfitters",
            "harbor_outfitters.*",
            "summit_financial",
            "summit_financial.*",
            "beacon_hq",
            "beacon_hq.*",
            "tests",
        ]
    ),
)
