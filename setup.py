
import setuptools

setuptools.setup(
    name='distributed-graph-routing',
    version='0.1.0',
    install_requires=[
        'apache-beam[gcp]',
        'networkx>=2.5',
    ],
    packages=['shared', 'contractions', 'serving_layer'],
)
