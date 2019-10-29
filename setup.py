from setuptools import setup, find_packages

setup(
      name='st_spin',
      version='0.0.1',
      url='https://github.com/m-laniakea/st_spin',
      license='GPLv1',
      author='eir',
      author_email='m-laniakea@users.noreply.github.com',
      description='Interface for ST SpinFamily motor drivers',
      packages=find_packages(exclude=['tests']),
      long_description=open('README.md').read(),
      zip_safe=False)