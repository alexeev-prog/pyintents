.. pyintents documentation master file

Welcome to pyintents's documentation!
======================================

PyIntents brings capability-based security to Python. Functions declare what they are allowed to do via @intent decorators, and the runtime enforces these permissions at call time. Define namespaces with allow and disallow rules, propagate restrictions recursively, or selectively exempt trusted functions with without. Permissions are dynamic and layered — grant or revoke access at runtime without touching the original code. Ideal for plugin sandboxes, AI agent tool control, environment-specific security policies, and testing. Trust explicitly, fail safely. No more functions that quietly do whatever they want.


.. note::
   This documentation is for version |version|.

Versions
--------

.. list-table::
   :header-rows: 1
   :widths: 20 60 20

   * - Version
     - Description
     - Status
   * - `main </pyintents/main/>`_
     - Latest development version from the main branch
     - **Latest**
   * - `v0.1.0 </pyintents/v0.1.0/>`_
     - Initial public release
     - Legacy

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   source/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
