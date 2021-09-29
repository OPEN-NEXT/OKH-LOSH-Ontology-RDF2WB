#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2021 Robin Vobruba <hoijui.quaero@gmail.com>
#
# SPDX-License-Identifier: CC-BY-SA-4.0

'''
Converts the OKH RDF Ontology into items and properties in a WikiBase instance.
It reads input from an RDF(/Turtle) file,
and writes appropriate items and properties into a WikiBase instance
through its API (api.php).
'''

import os
import pprint
import validators
import rdflib
from rdflib.namespace import DC, DCTERMS, DOAP, FOAF, SKOS, OWL, RDF, RDFS, VOID, XMLNS, XSD
import click
from wikibase import WBSession, DummyWBSession, API_URL_OHO, enable_debug, is_debug

OBO = rdflib.Namespace('http://purl.obolibrary.org/obo/')
SCHEMA = rdflib.Namespace('http://schema.org/')
SPDX = rdflib.Namespace('http://spdx.org/rdf/terms#')
EPO = rdflib.Namespace('http://data.epo.org/linked-data/def/patent/')

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option()
def version_token():
    '''
    Stub to set context settings and version info.
    '''
    #pass

RDF_FILE_LOCAL = '../LOSH/OKH-LOSH.ttl'
RDF_FILE_REMOTE = 'https://raw.githubusercontent.com/OPEN-NEXT/OKH-LOSH/master/OKH-LOSH.ttl'
RDF_FILE = RDF_FILE_LOCAL if os.path.exists(RDF_FILE_LOCAL) else RDF_FILE_REMOTE
BASE_URI = 'https://github.com/OPEN-NEXT/OKH-LOSH/raw/master/OKH-LOSH.ttl'
RDF_TO_WB_LINK_FILE = 'ont2wb_links.ttl'


def get_label_preds():
    return [RDFS.label or SKOS.prefLabel or DCTERMS.title or DC.title]

def get_desc_preds():
    return [RDFS.comment or SKOS.definition or DCTERMS.description or DC.description]

def get_non_claim_preds():
    return get_label_preds() + get_desc_preds() + [RDF.type,
            #RDFS.range, RDFS.domain,
            OWL.cardinality, OWL.maxCardinality, OWL.minCardinality]
            #RDFS.subPropertyOf, RDFS.subClassOf]

WD_PRED_IDS = ['P279', 'P1647', 'P305', 'P348', 'P144', 'P3931', 'P2479', 'P548', 'P4765', 'P527', 'P1324', 'P8203', 'P7535', 'P1114', 'P2699', 'P2479', 'P5778']

class RdfOntology2WikiBaseConverter:

    def __init__(self, ttl_source, wbs, link_graph_file):
        self.graph = rdflib.Graph()
        self.graph.load(ttl_source, format='turtle')
        self.wbs = wbs
        self.link_graph_file = link_graph_file
        self.ont2wb = rdflib.Graph()
        self.default_language = 'en'
        self.label_sep = '\n\n'
        self.description_sep = '\n\n'
        self.pp = pprint.PrettyPrinter(indent=4)

    def create_ont_wb_thing(self, subj) -> str:
        lbs = {}
        for lb_prop in get_label_preds():
            for lb in self.graph.objects(subj, lb_prop):
                lng = lb.language if lb.language is not None else self.default_language
                lbs[lng] = ((lbs[lng] + self.label_sep) if lng in lbs else '') + lb.value

        dscs = {}
        for dc_prop in get_desc_preds():
            for dc in self.graph.objects(subj, dc_prop):
                lng = dc.language if dc.language is not None else self.default_language
                dscs[lng] = ((dscs[lng] + self.description_sep) if lng in dscs else '') + dc.value

        types = list(self.graph.objects(subj, RDF.type))
        if OWL.Class in types:
            item = True
        elif (OWL.ObjectProperty in types) or (OWL.DatatypeProperty in types):
            item = False
        elif OWL.Ontology in types:
            return None
        else:
            print('RDF subject has unknown type: %s' % subj)
            for typ in types:
                print('\t%s' % typ)
            exit(1)

        return self.wbs.create_wb_thing(item=item, labels=lbs, descriptions=dscs, claims={})

    def skip_subj(self, subj):
        # It is either of:
        # * a blank-node (at the time of writing (24. august 2021), these are the `owl:unionOf`s from the `rdfs:range`s, which we ignore anyway
        # * the `owl:Ontology` instance
        #return (type(subj) is rdflib.term.BNode) or (str(subj) == BASE_URI)
        skip = (type(subj) is rdflib.term.BNode) or (str(subj) == BASE_URI)
        return skip

    def rdf2wb_id(self, rdf_ref, fail_if_missing=True):
        wb_ids = self.ont2wb.objects(rdf_ref, SCHEMA.identifier)
        if wb_ids is not None:
            wb_ids = list(wb_ids)
            if len(wb_ids) == 1:
                return str(wb_ids[0])
        if fail_if_missing:
            raise RuntimeError(
                    'We do not have a (single) WikiBase ID for RDF reference %s'
                    % rdf_ref)
        return None

    def create_claim(self, wb_id, subj, pred, obj):
        if pred in get_non_claim_preds():
            return
        claims = {}
        pred_wb_id = self.rdf2wb_id(pred)
        if pred_wb_id == 'P1647':
            print("WARNING: Not mapping wikidata.org property %s" % pred_wb_id)
            return
        value_type = None
        if isinstance(obj, rdflib.Literal):
            if validators.url(obj.n3()):
                value_type = 'url'
            else:
                value_type = 'string'
        else:
            types = list(self.graph.objects(obj, RDF.type))
            if OWL.Class in types:
                value_type = 'item'
            elif (OWL.ObjectProperty in types) or (OWL.DatatypeProperty in types):
                value_type = 'property'
            else:
                import re
                rdf_name = obj.n3()
                rdf_name = re.sub(r".*[#/]", "", rdf_name)
                if rdf_name[0].isupper():
                    value_type = 'item'
                else:
                    value_type = 'property'
        if value_type == 'string':
            main_value = str(obj)
        elif value_type == 'url':
            main_value = str(obj)
        else:
            obj_id = self.rdf2wb_id(obj)
            obj_id_num = int(obj_id[1:])
            main_value = {
                'entity-type': value_type,
                'id': obj_id,
                'numeric-id': obj_id_num
                }
        if value_type in ['string', 'url']:
            main_data_type = value_type
        else:
            main_data_type = 'wikibase-%s' % value_type
        main_type = value_type if value_type in ['string', 'url'] else 'wikibase-entityid'
        main_snak_type = 'value'
        '''
commonsMedia
entity-schema
external-id
globe-coordinate
geo-shape
wikibase-item
monolingualtext
time
wikibase-property
quantity
string
tabular-data
url
        '''
        claims[pred_wb_id] = [{
            #'id': '', # TODO
            'mainsnak': {
                'snaktype': main_snak_type,
                'property': pred_wb_id,
                'datatype': main_data_type,
                'datavalue': {
                    'value': main_value,
                    'type': main_type
                    }
                },
            'type': 'statement',
            'rank': 'normal',
            }]
        print('- Adding claim %s on %s' % (str(pred), wb_id), end = '')
        if is_debug():
            print('')
            print('    ', end = '')
            self.pp.pprint(claims)
        print(' ...')
        self.wbs.add_wb_thing_claims(wb_id, claims)

    def create_subst_property(self, rdf_pred_node, original_wd_id, label, obj_type):
        if self.rdf2wb_id(rdf_pred_node, fail_if_missing=False) is not None:
            return

        lbs = {}
        lbs[self.default_language] = label

        dscs = {}

        item = False

        property_type = obj_type if obj_type in ['string', 'url'] else 'wikibase-' + obj_type

        local_wb_id = self.wbs.create_wb_thing(item=item, labels=lbs, descriptions=dscs, claims={}, property_type=property_type)

        self.ont2wb.add((rdf_pred_node, SCHEMA.identifier, rdflib.Literal(local_wb_id)))

    def create_subst_item(self, rdf_indiv_node, original_wd_id, label, obj_type):
        if self.rdf2wb_id(rdf_indiv_node, fail_if_missing=False) is not None:
            return

        lbs = {}
        lbs[self.default_language] = label
        dscs = {}
        item = True

        local_wb_id = self.wbs.create_wb_thing(item=item, labels=lbs, descriptions=dscs, claims={})

        self.ont2wb.add((rdf_indiv_node, SCHEMA.identifier, rdflib.Literal(local_wb_id)))

    def convert(self):
        self.ont2wb = rdflib.Graph()
        if os.path.exists(self.link_graph_file):
            self.ont2wb.load(self.link_graph_file, format='turtle')
        else:
            self.create_subst_property(RDFS.subClassOf, 'P279', 'subClassOf', 'item') # https://www.wikidata.org/wiki/Property:P279
            self.create_subst_property(RDFS.subPropertyOf, 'P1647', 'subPropertyOf', 'property') # https://www.wikidata.org/wiki/Property:P1647
            #self.create_subst_property(SCHEMA.domain, SCHEMA.identifier, '')) #
            #self.create_subst_property(SCHEMA.range, SCHEMA.identifier, '')) # -> datatype
            self.create_subst_property(SCHEMA.inLanguage, 'P305', 'inLanguage',
                    'string') # https://www.wikidata.org/wiki/Property:P305
            self.create_subst_property(SCHEMA.version, 'P348', 'version',
                    'string') # https://www.wikidata.org/wiki/Property:P348
            self.create_subst_property(SCHEMA.isBasedOn, 'P144', 'isBasedOn',
                    'property') # https://www.wikidata.org/wiki/Property:P144
            self.create_subst_property(SCHEMA.copyrightHolder,
                    'P3931', 'copyrightHolder', 'item') # https://www.wikidata.org/wiki/Property:P3931
            self.create_subst_property(SCHEMA.licenseDeclared,
                    'P2479', 'licenseDeclared', 'item') # https://www.wikidata.org/wiki/Property:P2479
            self.create_subst_property(SCHEMA.creativeWorkStatus,
                    'P548', 'creativeWorkStatus', 'string') # https://www.wikidata.org/wiki/Property:P548 - aka version type
            self.create_subst_property(SCHEMA.image, 'P4765', 'image',
                    'url') # https://www.wikidata.org/wiki/Property:P4765 - aka Commons compatible image available at URL
            self.create_subst_property(SCHEMA.hasPart, 'P527', 'hasPart',
                    'item') # https://www.wikidata.org/wiki/Property:P527 - has part
            #self.create_subst_property(SCHEMA.hasPart, 'P2670', '', True) # https://www.wikidata.org/wiki/Property:P2670 - has parts of the class
            self.create_subst_property(SCHEMA.codeRepository,
                    'P1324', 'sourceCodeRepository', 'url') # https://www.wikidata.org/wiki/Property:P1324 - source code repository
            self.create_subst_property(SCHEMA.value, 'P8203',
                    'supportedMetaData',
                    'string') # https://www.wikidata.org/wiki/Property:P8203 -  aka supported Metadata
            self.create_subst_property(OBO.BFO_0000016, 'P7535',
                    'scopeAndContent',
                    'string') # function -> https://www.wikidata.org/wiki/Property:P7535 - aka scope and content
            self.create_subst_property(SCHEMA.amount, 'P1114',
                    'quantity',
                    'string') # https://www.wikidata.org/wiki/Property:P1114 -  aka quantity
            self.create_subst_item(SCHEMA.URL, 'QXXXXXXX', 'URL',
                    None) # https://www.wikidata.org/wiki/Property:P2699 -  aka URL
            self.create_subst_property(SPDX.licenseDeclared, 'P2479',
                    'licenseDeclared', 'string')
            self.create_subst_property(EPO.classificationIPCInventive, 'P5778',
                    'classificationIPCInventive', 'string')
            self.create_subst_property(SCHEMA.fileFormat, 'PXXXXXX', 'fileFormat',
                    'string')

        # create the items and properties
        for subj in self.graph.subjects():
            if self.skip_subj(subj):
                continue
            wb_ids = list(self.ont2wb.objects(subj, SCHEMA.identifier))
            wb_id = wb_ids[0] if len(wb_ids) > 0 else None
            if wb_id is None:
                print('- Creating WB part for subject "%s" ...' % subj)
                wb_id = self.create_ont_wb_thing(subj)
                self.ont2wb.add((subj, SCHEMA.identifier, rdflib.Literal(wb_id)))
            #else: # XXX We might want to recreate it here, anyway!
            print('- Subject "%s" is represented by "%s"' % (subj, wb_id))

        self.ont2wb.serialize(self.link_graph_file, format='turtle')

        # Create the connections/predicates/claims
        for subj in self.graph.subjects():
            if self.skip_subj(subj):
                continue
            wb_ids = list(self.ont2wb.objects(subj, SCHEMA.identifier))
            wb_id = wb_ids[0]
            if isinstance(wb_id, rdflib.Literal):
                wb_id = str(wb_id)
            for _, pred, obj in self.graph.triples((subj, None, None)):
                if pred == RDFS.range:
                    if is_debug():
                        print('XXX range')
                elif pred == RDFS.domain:
                    if is_debug():
                        print('XXX domain')
                else:
                    self.create_claim(wb_id, subj, pred, obj)

        print('done.')

@click.command(context_settings=CONTEXT_SETTINGS)
@click.argument('user', envvar='USER')
@click.argument('passwd', envvar='PASSWD')
@click.option('-d', '--dry', default=False, is_flag=True)
@click.option('-d', '--debug', default=False, is_flag=True)
@click.version_option("1.0.1")
def cli(user, passwd, dry, debug):
    # Run as a CLI script
    if debug:
        enable_debug()

    if dry:
        wbs = DummyWBSession(API_URL_OHO)
    else:
        wbs = WBSession(API_URL_OHO)
        wbs.login(user, passwd)

    converter = RdfOntology2WikiBaseConverter(RDF_FILE, wbs, RDF_TO_WB_LINK_FILE)
    converter.convert()

if __name__ == "__main__":
    cli()
