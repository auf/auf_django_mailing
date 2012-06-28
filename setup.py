# encoding: utf-8

from setuptools import setup, find_packages

name = 'auf.django.mailing'
version = '0.3'

setup(
    name=name,
    version=version,
    description="Application de mailing",
    author='Béranger Enselme',
    author_email='beranger.enselme@auf.org',
    url='http://pypi.auf.org/%s' % name,
    license='GPL',
    packages=find_packages(exclude=['tests', 'tests.*']),
    namespace_packages=['auf', 'auf.django'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'setuptools',
        ]
)

