from setuptools import setup

setup(
    name='offpunk',
    version='0.3',
    description="Offline Command line Gemini client forked from AV-98.",
    author="Ploum",
    author_email="offpunk@ploum.eu",
    url='https://tildegit.org/ploum/AV-98-offline/',
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Communications',
        'Intended Audience :: End Users/Desktop',
        'Environment :: Console',
        'Development Status :: 4 - Beta',
    ],
    py_modules = ["offpunk"],
    entry_points={
        "console_scripts": ["offpunk=offpunk:main"]
    },
    install_requires=[],
)
