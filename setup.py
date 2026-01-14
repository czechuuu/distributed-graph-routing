
import setuptools

# NOTE: Keep these dependencies in sync with pyproject.toml
# See .agent/workflows/sync-dependencies.md for the sync workflow
setuptools.setup(
    name='distributed-graph-routing',
    version='0.1.0',
    install_requires=[
        'apache-beam[gcp]==2.70.0',
        'google-cloud-bigtable',
        'networkx>=2.5',
        'crcmod',
        'protobuf==6.31.1',
        'grpcio<1.66.0',  # Pinned for Apache Beam compatibility
        'pip',  # Required for Apache Beam stager
    ],
    packages=['shared', 'contractions', 'serving_layer'],
)
