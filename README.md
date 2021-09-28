<!--
SPDX-FileCopyrightText: 2021 Robin Vobruba <hoijui.quaero@gmail.com>

SPDX-License-Identifier: CC-BY-SA-4.0
-->

# OKH - LOSH - RDF Ontology to WikiBase converter

A [CLI](https://en.wikipedia.org/wiki/Command-line_interface)
tool to convert the [Open Know-How](https://openknowhow.org/)
[Library of Open Source Hardware](https://github.com/OPEN-NEXT/OKH-LOSH/)
(OKH-LOSH) ontology from [RDF](
https://en.wikipedia.org/wiki/Resource_Description_Framework)
into a WikiBase instance,
which is a non RDF [triple store](https://en.wikipedia.org/wiki/Triplestore)
(aka graph database).

## Whom this is for

This tool is interesting for admins of organisations
that want to store OKH meta-data in a WikiBase triple store.
It is also possible to use an RDF native triple store instead.

Given this target group,
the tool is kept bare-metal,
meaning it contains only the code doing the actual work
and a basic CLI interface.
It creates WikiBase properties and objects on the server,
and a lot of CLI output, but nothing else.

## Design Notes

This tool was specifically made for the OKH ontology,
and is not a general RDF to WikiBase converter,
neither for general RDF data nor for ontologies.
The reason for this, is that WikiBase does not use RDF,
yet it comes with some predefined base items and properties
It makes sense to use these, to be able to link to other ontologies,
which translates into adhering to the fifth-star requirements
for [linked-open-data](https://5stardata.info).
WikiBase uses a different base-items and properties structure
then the common ones used in the RDF world.
There is no inherent nor any explicit existing mapping between the two,
and realistically it is not possible to do that at all,
as there are inherent incompatibilities,
which are not solvable without changing the base structure
of at least one of these universes,
including all the data built on top of that base structure,
which would be virtually all data stored in RDF or WikiBase respectively.
As our data lives natively in the RDF universe,
we therefore chose to use a partial, specific mapping,
just for the part of the base structure we need.
This mapping is defined in the python code
of the [rdfont2wb.py](./rdfont2wb.py) tool in this repository.

**NOTE:** \
Due to the reasons explained above,
it is likely that the code of this tool has to be adapted
whenever we make structural changes to the OKH LOSH RDF ontology.
More specifically, the most likely thing to happen,
is that we link to additional, external RDF properties of classes,
and then need to define a mapping for that in the code of this tool,
most likely in the `convert` function of [rdfont2wb.py](./rdfont2wb.py).

## Installation

After locally cloning this repository,
run this to install the python dependencies:

```bash
sudo pip install -r requirements.txt
```

## Usage

This can be used to create the ontology from scratch,
or to update it - just run it! :-)

The command below reads our [OKH-LOSH.md](
https://github.com/OPEN-NEXT/OKH-LOSH/blob/master/OKH-LOSH.ttl)
OKH meta-data ontology file (format: RDF/Turtle),
and converts it to a quasi equivalent ontology on a WikiBase instance
through the [api.php](https://www.mediawiki.org/w/api.php) web interface.
It writes to our OHO WikiBase instance.
You will need an account with enough rights
on the WikiBase instance you want to import the ontology to.
Run this to start the importing process:

```bash
python3 rdfont2wb.py 'MyOhoUser' 'MyOhoPasswd'
```

If all goes well,
you will see a lot of CLI output
of parts of the ontology being created on the WikiBase instance.
In the end, you should get a non-zero exit status.
You may then inspect the generated ontology
on your WikiBase instances web interface.
