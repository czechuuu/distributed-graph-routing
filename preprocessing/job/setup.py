
import setuptools
import os

# NOTE: Keep these dependencies in sync with root setup.py
# Use package_dir to reference packages from the root directory
# This avoids code duplication while allowing the cloud function to package them
root_dir = os.path.join(os.path.dirname(__file__), '..', '..')

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
        'build', # Required for creating source distribution
    ],
    packages=['shared', 'contractions', 'serving_layer'],
    package_dir={
        'shared': os.path.join(root_dir, 'shared'),
        'contractions': os.path.join(root_dir, 'contractions'),
        'serving_layer': os.path.join(root_dir, 'serving_layer'),
    },
)
