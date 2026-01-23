import setuptools

setuptools.setup(
    name="legacy-graph-routing-pipeline",
    version="0.1.0",
    description="Legacy Bigtable pipeline",
    package_dir={"": "."},
    packages=setuptools.find_packages(),
    py_modules=["legacy_pipeline", "legacy_main", "io_wrappers"],
    install_requires=[],
)
