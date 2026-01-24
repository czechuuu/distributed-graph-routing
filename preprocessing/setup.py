import setuptools

setuptools.setup(
    name='distributed-graph-routing-preprocessing',
    version='0.1.0',
    description='Preprocessing pipeline for distributed graph routing',
    packages=setuptools.find_packages(),
    install_requires=[
        'apache-beam[gcp]>=2.70.0',
        'google-cloud-bigquery>=3.40.0',
        'google-cloud-bigtable>=2.35.0',
        'grpcio>=1.64.1',
        'igraph>=0.11.0',
        'protobuf>=5.26.1',
        's2sphere>=0.2.5',
        'osmium>=4.0.0',
        'pyarrow>=18.0.0',
    ],
)
