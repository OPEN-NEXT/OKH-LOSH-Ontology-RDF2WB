#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2021 Robin Vobruba <hoijui.quaero@gmail.com>
#
# SPDX-License-Identifier: CC-BY-SA-4.0

'''
Allows to conveniently interface with the WikiBase API.

see:
* https://www.mediawiki.org/wiki/Wikibase/DataModel/JSON
* https://wikibase.oho.wiki/index.php?title=Special:NewItem

* https://www.wikidata.org/w/api.php?action=help&modules=wbeditentity
* https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities
* https://www.wikidata.org/w/api.php?action=help&modules=wbsearchentities

* https://wikibase.oho.wiki/api.php?action=help&modules=wbeditentity
* https://wikibase.oho.wiki/api.php?action=help&modules=wbgetentities
* https://wikibase.oho.wiki/api.php?action=help&modules=wbsearchentities
'''

import json
import re
import logging
import requests
import random

try: # for Python 3
    from http.client import HTTPConnection
except ImportError:
    from httplib import HTTPConnection

API_URL_MEDIA_WIKI = 'https://www.wikidata.org/w/api.php'
API_URL_OHO = 'http://losh.ose-germany.de/api.php'

debug_enabled = False

def enable_debug():
    '''
    Enabling debugging at http.client level (requests->urllib3->http.client)
    you will see the REQUEST, including HEADERS and DATA,
    and RESPONSE with HEADERS but without DATA.
    the only thing missing will be the response.body which is not logged.
    '''
    global debug_enabled
    HTTPConnection.debuglevel = 1

    # you need to initialize logging,
    # otherwise you will not see anything from requests
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
    debug_enabled = True

def is_debug():
    '''
    Returns True if debugging is enabled, False otherwise.
    '''
    global debug_enabled
    return debug_enabled

class WBSession:
    '''
    Represents a session of HTTP communication with a Wiki-Base instance,
    through its "api.php".
    '''
    def __init__(self, api_url):
        self.http_sess = requests.Session()
        self.api_url = api_url

    def call_api(self, params=None, data=None, method='POST'):
        '''
        Calls the MediaWiki API (api.php) with the given parameters.
        '''
        req = self.http_sess.request(method=method, url=self.api_url, params=params, data=data)
        return req

    def close(self):
        '''
        Closes this session.
        After calling this, further use of other methods will fail.
        '''
        self.http_sess.close()

    def bot_login(self, bot_user, bot_passwd):
        '''
        see: https://www.mediawiki.org/wiki/API:Login#Method_1._login
        '''

        # Retrieve login token first
        params_login_token = {
            'action':"query",
            'meta':"tokens",
            'type':"login",
            'format':"json"
        }

        req = self.call_api(params=params_login_token)
        ans = req.json()
        login_token = ans['query']['tokens']['logintoken']
        #print(login_token)

        # Send a post request to login. Using the main account for login is not
        # supported. Obtain credentials via Special:BotPasswords
        # (https://www.mediawiki.org/wiki/Special:BotPasswords) for lgname & lgpassword
        params_login = {
            'action':"login",
            'lgname':bot_user,
            'lgpassword':bot_passwd,
            'lgtoken':login_token,
            'format':"json"
        }
        req = self.call_api(data=params_login)
        ans = req.json()
        #print(ans)

    def fetch_login_token(self) -> str:
        """ Fetch login token via `tokens` module """

        res = self.call_api(
            params={
                'action': "query",
                'meta': "tokens",
                'type': "login",
                'format': "json"})
        data = res.json()
        return data['query']['tokens']['logintoken']

    def login(self, username, password):
        """
        Send a post request along with login token, user information
        and return URL to the API to log in on a wiki

        https://www.mediawiki.org/wiki/API:Login#Method_2._clientlogin
        """

        login_token = self.fetch_login_token()

        response = self.call_api(
                data={
                    'action': "clientlogin",
                    'username': username,
                    'password': password,
                    'loginreturnurl': 'http://127.0.0.1:5000/',
                    'logintoken': login_token,
                    'format': "json"
                })

        data = response.json()

        login_success = data['clientlogin']['status'] == 'PASS'

        if login_success:
            print('Login success! Welcome, ' + data['clientlogin']['username'] + '!')
        else:
            raise RuntimeError('Failed to log into WikiBase at "%s", error: %s' %
                    (self.api_url, str(data['clientlogin']['messagecode'])))

    def request_token(self) -> str:
        '''
        Requests a standard token, required to do almost any interaction
        with the API.
        '''
        res = self.call_api(params={'action':'query', 'meta':'tokens', 'format':'json'})
        if res.status_code != 200:
            raise RuntimeError('Failed to get token; HTTP error: {}' % res.status_code)

        res_data = json.loads(res.content)
        return res_data['query']['tokens']['csrftoken']

    def clear_thing(self, part_id):
        '''
        Clears everything from an Item or Property.
        '''
        print('- Clear Item/Property with ID %s ...' % part_id)
        res = self.call_api(
                method='POST',
                params = {
                    'action': 'wbeditentity',
                    'id': part_id,
                    'clear': 'true',
                    'format':'json',
                    'data': '{}'
                },
                data = {'token': self.request_token()}
            )
        ans = res.json()
        if 'error' in ans:
            raise RuntimeError('Failed clearing Item/Property with ID %s, reason: %s - %s'
                    % (part_id, ans['error']['code'], ans['error']['info']))

    def add_wb_thing_claims(self, wb_id, claims={}):
        '''
        Adds claims to an item or property.
        '''
        data = { 'claims': claims }
        return self.create_wb_thing_raw(None, data, wb_id)

    def create_wb_thing_raw(self, item=True, data={}, wb_id=None) -> str:
        '''
        Creates a new WikiBase item or property.
        '''
        type_str = 'Item' if item else 'Property'
        print('- Creating %s ...' % type_str)
        print(json.dumps(data))
        params = {
            'action': 'wbeditentity',
            #'site': site,
            #'title': title,
            'format':'json',
            'data': json.dumps(data)
            }
        if wb_id is None:
            params['new'] = 'item' if item else 'property'
            params['clear'] = 'true'
        else:
            params['id'] = wb_id

        res = self.call_api(
                method = 'POST',
                params = params,
                data = {'token': self.request_token()}
            )
        ans = res.json()

        if 'error' in ans:
            #print(ans)
            if ' already has ' in ans['error']['info']:
                # Item/Property already exists.
                # -> Delete it and create it from anew.
                #    api.php?action=wbeditentity&clear=true&id=Q42&data={} [open in sandbox]
                item_pat = re.compile(r'\[\[Item:(Q[0-9]+)')
                prop_pat = re.compile(r'\[\[Property:(P[0-9]+)')
                pat = item_pat if item else prop_pat
                match = pat.search(ans['error']['info'])
                wb_id = match.group(1)
                self.clear_thing(wb_id)
                return self.create_wb_thing_raw(item, data, wb_id)
            raise RuntimeError('Failed creating %s, reason: %s - %s -\n%s'
                    % (type_str, ans['error']['code'], ans['error']['info'],
                       json.dumps(ans)))

        print(ans)
        return ans['entity']['id']

    def create_wb_thing(self, item=True, labels={}, descriptions={}, claims={}, property_type='string') -> str:
        '''
        Creates a WikiBase item or property,
        and returns its id (eg. "Q123456" or "P12345") if successful.
        @param property_type see the list at: https://wikibase.oho.wiki/index.php?title=Special:NewProperty
        '''
        data = {
                'labels': {},
                'descriptions': {},
                }
        if not item:
            data['datatype'] = property_type # see the following list (extracted from: https://wikibase.oho.wiki/index.php?title=Special:NewProperty )
        for label_lang in labels.keys():
            if isinstance(labels[label_lang], list):
                for i in range(0, len(labels[label_lang])):
                    data['labels'][label_lang] = {
                                'language': label_lang,
                                'value': labels[label_lang][i]
                            }
            else:
                data['labels'][label_lang] = {
                            'language': label_lang,
                            'value': labels[label_lang]
                        }
        for desc_lang in descriptions.keys():
            if isinstance(labels[desc_lang], list):
                for i in range(0, len(descriptions[desc_lang])):
                    data['descriptions'][desc_lang] = {
                                'language': desc_lang,
                                'value': descriptions[desc_lang][i]
                            }
            else:
                desc = descriptions[desc_lang]
                desc = (desc[:247] + '...') if len(desc) > 250 else desc
                data['descriptions'][desc_lang] = {
                            'language': desc_lang,
                            'value': desc
                        }
        return self.create_wb_thing_raw(item, data)

class DummyWBSession(WBSession):
    '''
    Represents a dummy session of HTTP communication with a Wiki-Base instance,
    meaning, it does not communicate with a server,
    but acts as if it did, as muhc as possible.
    '''
    def __init__(self, api_url):
        random.seed()
        self.api_url = api_url

    def call_api(self, params=None, data=None, method='POST'):
        '''
        Pseudo calls the MediaWiki API (api.php) with the given parameters.
        '''
        req = ""
        return req

    def close(self):
        '''
        Pseudo closes this session.
        After calling this, further use of other methods will fail.
        '''
        pass

    def bot_login(self, bot_user, bot_passwd):
        '''
        Pseudo function for logging in as a bot.
        '''
        pass

    def fetch_login_token(self) -> str:
        ''' Pseudo fetches login token '''
        return ""

    def login(self, username, password):
        """
        Pseudo send a post request along with login token, user information
        and return URL to the API to log in on a wiki

        https://www.mediawiki.org/wiki/API:Login#Method_2._clientlogin
        """
        pass

    def request_token(self) -> str:
        '''
        Pseudo requests a standard token, required to do almost any interaction
        with the API.
        '''
        return ""

    def clear_thing(self, part_id):
        '''
        Pseudo clears everything from an Item or Property.
        '''
        print('- Dry-Clear Item/Property ...')

    def add_wb_thing_claims(self, wb_id, claims={}):
        '''
        Pseudo adds claims to an item or property.
        '''
        return ""

    def create_wb_thing_raw(self, item=True, data={}, wb_id=None) -> str:
        '''
        Pseudo creates a new WikiBase item.
        '''
        print('- Dry-Creating %s ...' % ('Item' if item else 'Property'))
        return ("Q" if item else "P") + random.randint(100, 1000)

    # def create_wb_thing(self, item=True, labels={}, descriptions={}, claims={}, property_type='string') -> str:
    #     NOTE Us eparents implementation

if __name__ == "__main__":
    # Run as a CLI script
    SAMPLE_DATA = '''
    {
      "labels": {
        "en": {
          "language": "en",
          "value": "New York City"
        },
        "ar": {
          "language": "ar",
          "value": "\u0645\u062f\u064a\u0646\u0629 \u0646\u064a\u0648 \u064a\u0648\u0631\u0643"
        }
      },
      "descriptions": {
        "en": {
          "language": "en",
          "value": "largest city in New York and the United States of America"
        },
        "it": {
          "language": "it",
          "value": "citt\u00e0 degli Stati Uniti d'America"
        }
      },
      "aliases": {
        "en": [
          {
            "language": "en",
            "value": "NYC"
          },
          {
            "language": "en",
            "value": "New York"
          },
        ],
        "fr": [
          {
            "language": "fr",
            "value": "New York City"
          },
          {
            "language": "fr",
            "value": "NYC"
          },
          {
            "language": "fr",
            "value": "The City"
          },
          {
            "language": "fr",
            "value": "City of New York"
          },
          {
            "language": "fr",
            "value": "La grosse pomme"
          }
        ]
      }
      "claims": {
        "P17": [
          {
            "id": "q60$5083E43C-228B-4E3E-B82A-4CB20A22A3FB",
            "mainsnak": {},
            "type": "statement",
            "rank": "normal",
            "qualifiers": {
              "P580": [],
              "P5436": []
             }
            "references": [
               {
                 "hash": "d103e3541cc531fa54adcaffebde6bef28d87d32",
                 "snaks": []
               }
             ]
          }
        ]
      }
    }
    '''
    '''
    SAMPLE_DATA = '{}'
    #ITEM_TITLE = 'TEST_EMPTY'
    #SITE = 'oho'

    #enable_debug()
    wbs = WBSession(API_URL_OHO)
    #wbs.bot_login(bot_user, bot_passwd)
    wbs.login(USER, PASSWD)
    #item_id = wbs.create_item(SITE, ITEM_TITLE, SAMPLE_DATA)
    item_id = wbs.create_item(SAMPLE_DATA)

    print(item_id)
    '''
