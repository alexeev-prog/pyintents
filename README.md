<a id="readme-top"></a>

<div align="center">
  <p align="center">
    <h1>pyintents</h1>
    <p>Declarative capability-based access control for Python functions.</p>
    <a href="https://alexeev-prog.github.io/pyintents/v0.2.2"><strong>Explore the docs »</strong></a>
  </p>
  <p align="center">
    <a href="#-getting-started">Getting Started</a>
    ·
    <a href="#-basic-usage">Basic Usage</a>
    ·
    <a href="https://alexeev-prog.github.io/pyintents/main">Latest Documentation</a>
    ·
    <a href="https://github.com/alexeev-prog/pyintents/blob/main/LICENSE">License</a>
  </p>
</div>
<hr>
<p align="center">
    <img src="https://img.shields.io/github/languages/top/alexeev-prog/pyintents?style=for-the-badge">
    <img src="https://img.shields.io/github/languages/count/alexeev-prog/pyintents?style=for-the-badge">
    <img src="https://img.shields.io/badge/Maintained-yes-green.svg?style=for-the-badge">
    <img alt="GitHub License" src="https://img.shields.io/github/license/alexeev-prog/pyintents?style=for-the-badge&logo=gnu">
    <img alt="GitHub forks" src="https://img.shields.io/github/forks/alexeev-prog/pyintents?style=for-the-badge&logo=github">
    <img src="https://img.shields.io/github/stars/alexeev-prog/pyintents?style=for-the-badge">
    <img src="https://img.shields.io/github/issues/alexeev-prog/pyintents?style=for-the-badge">
    <img src="https://img.shields.io/github/last-commit/alexeev-prog/pyintents?style=for-the-badge">
    <img alt="GitHub commits since latest release" src="https://img.shields.io/github/commits-since/alexeev-prog/pyintents/latest?style=for-the-badge">
    <img alt="GitHub Release Date" src="https://img.shields.io/github/release-date-pre/alexeev-prog/pyintents?style=for-the-badge">
    <img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/alexeev-prog/pyintents/docs.yml?style=for-the-badge&logo=github&label=docs">
    <img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/alexeev-prog/pyintents/python-package.yml?style=for-the-badge&logo=python&label=python%20package%20lint">
    <img src="https://img.shields.io/pypi/wheel/pyintents?style=for-the-badge">
    <img alt="PyPI - Downloads" src="https://img.shields.io/pypi/dm/pyintents?style=for-the-badge">
    <img alt="PyPI - Version" src="https://img.shields.io/pypi/v/pyintents?style=for-the-badge">
    <img alt="GitHub contributors" src="https://img.shields.io/github/contributors/alexeev-prog/pyintents?style=for-the-badge">
</p>
<p align="center">
    <img src="https://raw.githubusercontent.com/alexeev-prog/pyintents/refs/heads/main/docs/pallet-0.png">
</p>


PyIntents brings capability-based security to Python. Functions declare what they are allowed to do via @intent decorators, and the runtime enforces these permissions at call time. Define namespaces with allow and disallow rules, propagate restrictions recursively, or selectively exempt trusted functions with without. Permissions are dynamic and layered — grant or revoke access at runtime without touching the original code. Ideal for plugin sandboxes, AI agent tool control, environment-specific security policies, and testing. Trust explicitly, fail safely. No more functions that quietly do whatever they want.
