
import setuptools

setuptools.setup(
    name='distributed-graph-routing',
    version='0.1.0',
    install_requires=[
        'apache-beam[gcp]',
        'google-cloud-bigtable',
        'networkx>=2.5',
        'crcmod',
        'protobuf==6.31.1',
    ],
    packages=['shared', 'contractions', 'serving_layer'],
)
