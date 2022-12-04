#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  This file is part of the `pypath` python module
#
#  Copyright
#  2014-2022
#  EMBL, EMBL-EBI, Uniklinik RWTH Aachen, Heidelberg University
#
#  Authors: Dénes Türei (turei.denes@gmail.com)
#           Nicolàs Palacio
#           Sebastian Lobentanzer
#           Erva Ulusoy
#           Olga Ivanova
#           Ahmet Rifaioglu
#           Melih Darcan
#
#  Distributed under the GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.organism/licenses/gpl-3.0.html
#
#  Website: http://pypath.omnipathdb.organism/
#

from __future__ import annotations

import collections
import itertools
import csv
import re
import asyncio

from concurrent.futures.thread import ThreadPoolExecutor

from abc import ABC, abstractmethod
from typing import Iterable, Literal

import pypath.resources.urls as urls
import pypath.share.curl as curl
import pypath.share.session as session
import pypath.share.common as common

_logger = session.Logger(name = 'kegg_api')
_log = _logger._log

_url = urls.urls['kegg_api']['url']


def gene_to_pathway(organism):

    return _kegg_relations('gene', 'pathway', organism)


def pathway_to_gene(organism):

    return _kegg_relations('pathway', 'gene', organism)


def gene_to_drug(organism):

    return _kegg_relations('gene', 'drug', organism)


def drug_to_gene(organism):

    return _kegg_relations('drug', 'gene', organism)


def gene_to_disease(organism):

    return _kegg_relations('gene', 'disease', organism)


def disease_to_gene(organism):

    return _kegg_relations('disease', 'gene', organism)


def pathway_to_drug():

    return _kegg_relations('pathway', 'drug')


def drug_to_pathway():

    return _kegg_relations('drug', 'pathway')


def pathway_to_disease():

    return _kegg_relations('pathway', 'disease')


def disease_to_pathway():

    return _kegg_relations('disease', 'pathway')


def disease_to_drug():

    return _kegg_relations('disease', 'drug')


def drug_to_disease():

    return _kegg_relations('drug', 'disease')


def drug_to_drug(
    drugs: list | tuple | None = None,
    join: bool = True,
    asynchronous: bool = False
) -> dict[str, tuple]:
    """
    Downloads drug-drug interaction data from KEGG database.

    Args
        drugs:
            Drug IDs as a list or a tuple.
        join:
            If it's True, returns individual interactions of queried list.
            Else, joins them together and returns mutual interactions.
        asynchronous:
            Yet to be implemented.

    Returns
        A dict with disease IDs as keys and drug-drug interactions as values.
    """

    DrugToDrugInteraction = collections.namedtuple(
        'DrugToDrugInteraction',
        (
            'type',
            'name',
            'interactions',
        ),
    )

    Interaction = collections.namedtuple(
        'Interaction',
        (
            'type',
            'id',
            'name',
            'contraindication',
            'precaution',
        )
    )

    entry_types = {'d': 'drug', 'c': 'compound'}
    entry_dbs = {'drug': _Drug(), 'compound': _Compound()}
    interactions = collections.defaultdict(
        lambda: {
            'interactions': collections.defaultdict(list),
        }
    )

    join = join and drugs
    asynchronous = not drugs or asynchronous
    drugs = drugs or entry_dbs['drug'].get_data().keys()
    entries = _kegg_ddi(drugs, join = join, asynchronous=asynchronous)

    for entry in entries:

        partners = dict(
            (
                role,
                {
                    'type': entry_types.get(entry[i][0].lower(), None),
                    'id': entry[i].split(':')[-1],
                    'name': entry_dbs[entry_type].get(entry_id, None)
                }
            )
            for i, role in enumerate(('source', 'target'))
        )

        labels = entry[2].split(',')
        contraindication = 'CI' in labels
        precaution = 'P' in labels

        interaction = Interaction(
            type = partners['target']['type'],
            id = partners['target']['id'],
            name = partners['target']['name'],
            contraindication = contraindication,
            precaution = precaution,
        )

        disease_id = partners['source']['id']
        interactions[disease_id]['interactions'].append(interaction)
        interactions[disease_id]['type'] = partners['source']['type']
        interactions[disease_id]['name'] = partners['source']['name']

    interactions = dict(
        (
            key,
            DrugToDrugInteraction(
                value['type'],
                value['name'],
                tuple(value['interactions']),
            )
        )
        for key, value in interactions.items()
    )

    return interactions


def kegg_gene_id_to_ncbi_gene_id(organism):

    return _kegg_conv(organism, 'ncbi-geneid', target_split=True)


def ncbi_gene_id_to_kegg_gene_id(organism):

    return _kegg_conv('ncbi-geneid', organism, source_split=True)


def kegg_gene_id_to_uniprot_id(organism):

    return _kegg_conv(organism, 'uniprot', target_split=True)


def uniprot_id_to_kegg_gene_id(organism):

    return _kegg_conv('uniprot', organism, source_split=True)


def kegg_drug_id_to_chebi_id():

    return _kegg_conv('drug', 'chebi', source_split=True, target_split=True)


def chebi_id_to_kegg_drug_id():

    return _kegg_conv('chebi', 'drug', source_split=True, target_split=True)


async def _kegg_general(
    operation: str,
    *arguments: str,
    async_: bool = False,
) -> list[list[str]]:

    url = '/'.join([_url % operation] + arguments)
    curl_args = {'url': url, 'silent': True, 'large': False}

    if _async:
        c = await curl.Curl(**curl_args)
    else:
        c = curl.Curl(**curl_args)

    lines = getattr(c, 'result', []) or []

    return [line.split('\t') for line in lines if line]


async def _kegg_general_async(
    operation: str,
    *arguments: str,
) -> list[list[str]]:

    #TODO Yet to be implemented
    # This function doesn't work but it better
    # stay so we can implement it without
    # changing the structure of the module

    return _kegg_general(operation, *arguments, async_ = False)


def _kegg_list(
    database: str,
    option: str | None = None,
    organism: str | int | None = None,
) -> list[list[str]]:

    args = (
        ['list', database] +
        common.to_list(option) if database == 'brite' else [] +
        common.to_list(organism) if database == 'pathway' else []
    )

    return _kegg_general(*args)


def _kegg_conv(
    source_db: str,
    target_db: str,
    source_split: bool = False,
    target_split: bool = False,
) -> dict[str, set[str]]:

    result = _kegg_general('conv', target_db, source_db)
    conversion_table = collections.defaultdict(set)

    for source, target in result:

        source = source.split(':')[1] if source_split else source
        target = target.split(':')[1] if target_split else target
        conversion_table[source].add(target)

    return dict(conversion_table)


def _kegg_link(source_db: str, target_db: str) -> list[list[str]]:

    return _kegg_general('link', target_db, source_db)


def _kegg_ddi(drug_ids: str | Iterable[str], async_: bool = False):

    drug_ids = '+'.join(common.to_list(drug_ids))

    if async_:

        pool = ThreadPoolExecutor()

        return pool.submit(asyncio.run, _kegg_ddi_async(drug_ids)).result()

    return _kegg_ddi_sync(drug_ids)


def _kegg_ddi_sync(drug_ids: str | Iterable[str]):

    return list(itertools.chain(*(
        _kegg_general('ddi', drug_id)
        for drug_id in common.to_list(drug_ids)
    )))


async def _kegg_ddi_async(drug_ids):

    #TODO Yet to be implemented
    # This function doesn't work but it better
    # stay so we can implement it without
    # changing the structure of the module

    result = []

    for response in asyncio.as_completed([
        _kegg_general_async('ddi', drug_id)
        for drug_id in common.to_list(drug_ids)
    ]):
        the_response = await response
        result.extend(common.to_list(the_response))

    return result


def _kegg_relations(
    source_db: Literal['gene', 'pathway', 'disease', 'drug'],
    target_db: Literal['gene', 'pathway', 'disease', 'drug'],
    # should have human as a default, instead of triggering an error:
    organism: str | None = None,
) -> tuple:

    l_organism = common.to_list(organism)
    data = {}

    record = collections.namedtuple(
        'KeggEntry',
        (
            'id',
            'name',
            'type',
            'ncbi_gene_ids',
            'uniprot_ids',
            'chebi_ids',
        )
    )


    def get_data(name, cls_prefix = ''):

        if name not in data:

            cls = f'_{cls_prefix}{name.capitalize()}'
            data[name] = locals()[cls](*l_organism)

        return data[name]

    def db(name):

        return get_data(name)


    def ids(name):

        return get_data(name, cls_prefix = 'KeggTo')


    def process(entry, type_):

        id_ = db(type_).handle(entry)
        name = db(type_).get(id_, None)
        ncbi = ids('ncbi').get(id_) if type_ == 'gene' else ()
        uniprot = ids('uniprot').get(id_) if type_ == 'gene' else ()
        chebi = ids('chebi').get(id_) if type_ == 'drug' else ()

        return record(
            id = id_,
            name = name,
            type = type_,
            ncbi_gene_ids = ncbi,
            uniprot_ids = uniprot,
            chebi_ids = chebi,
        )


    args = [organism if db == 'gene' else db for db in (source_db, target_db)]
    entries = _kegg_link(*args)
    interactions = [(process(e[0]), process(e[1])) for e in entries]

    return interactions


class _KeggDatabase(ABC):

    _data = None
    _query_args = None


    @abstractmethod
    def __init__(self, *args):

        self.load(*args)


    @abstractmethod
    def proc_key(self, entry):

        return entry


    @abstractmethod
    def proc_value(self, entry):

        return entry


    @abstractmethod
    def load(self, *args):

        entries = _kegg_list(*common.to_list(self._query_args), *args)

        self._data = {
            self.proc_key(entry): self.proc_value(entry)
            for entry in entries
        }


    def get(self, index, default = None):

        return self._data.get(index, default)


    def __getitem__(self, index):

        return self.get(index)


    @property
    def data(self):

        return self._data


class _Organism(_KeggDatabase):

    _query_args = 'organism'


    def proc_value(self, entry):

        return (entry[0], entry[2])


    def proc_key(self, entry):

        return entry[1]


class _Gene(_KeggDatabase):


    def __init__(self, organism):

        super().__init__(organism)


    def proc_key(self, entry):

        return entry[0]


    def proc_value(self, entry):

        return entry[-1].rsplit(';', maxsplit = 1)[-1].strip(' ')


class _Pathway(_KeggDatabase):

    _re_pathway = re.compile(r'\d+')
    _query_args = 'pathway'


    def proc_value(self, entry):

        return entry[1]


    def proc_key(self, entry):

        pathway_id = self._re_pathway.search(entry[0])

        # is this correct?
        # there are pathway prefixes in KEGG other than "map"
        return f'map{pathway_id.group()}'


class _SplitDatabase(_KeggDatabase):


    def proc_key(self, entry):

        return entry[0].split(':')[1]


    def proc_value(self, entry):

        return entry[1]


class _Disease(_SplitDatabase):

    _query_args = 'disease'


class _Drug(_SplitDatabase):

    _query_args = 'drug'


class _Compound(_SplitDatabase):

    _query_args = 'compound'


class _ConversionTable:

    _table = dict()

    def __init__(self):
        self.download_table()


    @abstractmethod
    def download_table(self):
        pass


    def get(self, index):
        try:
            return self._table[index]
        except KeyError:
            return None


    def get_table(self):
        return self._table


class _OrgTable(_ConversionTable):

    def __init__(self, organism=None):
        if organism is not None:
            self.download_table(organism)


class _KeggToNcbi(_OrgTable):

    def download_table(self, organism):
        table = _kegg_conv(organism, 'ncbi-geneid', target_split=True)
        self._table.update(table)


class _NcbiToKegg(_OrgTable):

    def download_table(self, organism):
        table = _kegg_conv('ncbi-geneid', organism, source_split=True)
        self._table.update(table)


class _KeggToUniprot(_OrgTable):

    def download_table(self, organism):
        table = _kegg_conv(organism, 'uniprot', target_split=True)
        self._table.update(table)


class _UniprotToKegg(_OrgTable):

    def download_table(self, organism):
        table = _kegg_conv('uniprot', organism, source_split=True)
        self._table.update(table)


class _KeggToChebi(_ConversionTable):

    def download_table(self):
        table = _kegg_conv('drug', 'chebi', source_split=True, target_split=True)
        self._table = table


class _ChebiToKegg(_ConversionTable):

    def download_table(self):
        table = _kegg_conv('chebi', 'drug', source_split=True, target_split=True)
        self._table = table
