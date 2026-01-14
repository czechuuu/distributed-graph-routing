import setuptools

setuptools.setup(
    name='distributed-graph-routing',
    version='0.1.0',
    install_requires=[
        'apache-beam[gcp]>=2.61.0',
        'google-cloud-bigtable',
        'networkx>=2.5',
        'protobuf>=4.25.3,<5.0.0',
        'grpcio<1.66.0',
    ],
    
    packages=setuptools.find_packages(), 
)