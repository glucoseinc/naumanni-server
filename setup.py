#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup


install_requires = [
    'celery>=4',
    'celery[redis]',
    'click>=6',
    'Flask>=0.12',
    'pycurl>=7.43.0',
    'python-dateutil>=2.6.0',
    'redis>=2.10',
    'tornado>=4.5.1',
    'twitter-text-python>=1.1.0',
]

setup(
    name='naumanni-server',
    version='0.1',
    packages=find_packages(exclude=['tests']),
    install_requires=install_requires,
    dependency_links=[
        # 'git+https://github.com/nanomsg/nnpy.git#egg=nnpy',
        # 'git+https://github.com/graphite-project/whisper.git@b783ab3f577f3f60db607adda241e29b7242bcf4#egg=whisper-0.10.0rc1',
    ],
    entry_points={
        'console_scripts': [
            'naumanni=naumanni.cli:cli_entry',
        ],
    },
    extras_require={
        'test': [
            'coverage',
            'flake8',
            'flake8-import-order',
            # 'nnpy',
            'pytest',
            # 'pytest-timeout',
            # 'tcptest',
            'tox',
        ],
        'doc': [
            # 'Sphinx',
            # 'sphinx-rtd-theme',
        ],
        'utils': [
            'boto>=2.47.0',
        ]
    }
)
