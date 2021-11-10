#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  This file is part of the `pypath` python module
#  Provides classes for each database for annotations of proteins and complexes.
#  Also provides meta-annotations for the databases.
#
#  Copyright
#  2014-2021
#  EMBL, EMBL-EBI, Uniklinik RWTH Aachen, Heidelberg University
#
#  File author(s): Dénes Türei (turei.denes@gmail.com)
#                  Nicolàs Palacio
#                  Olga Ivanova
#
#  Distributed under the GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.org/licenses/gpl-3.0.html
#
#  Website: http://pypath.omnipathdb.org/
#

from future.utils import iteritems

import json
import itertools

import pypath.share.common as common


class AttributeHandler(object):
    """
    Base class for other classes which carry custom attributes (data) in a
    dedicated dict under the `attrs` attribute.
    """

    __slots__ = [
        'attrs',
    ]


    def __init__(self, attrs):

        self.attrs = attrs or {}


    def update_attrs(attrs = None, **kwargs):
        """
        Updates the attributes stored here. The attributes with identical
        keys are merged using the :py:func:`pypath.share.common.combine_attrs`
        function.

        The new attributes can be provided three ways: an object with an
        attribute called `attrs`; a dictionary of attributes; or the
        attributes as keyword arguments.
        """

        if hasattr(attrs, 'attrs'):

            attrs = attrs.attrs

        attrs = attrs or {}

        attrs.update(kwargs)

        self._update_attrs(attrs)


    def _update_attrs(attrs):

        for key, val in iteritems(kwargs):

            if key in self.attrs:

                self.attrs[key] = common.combine_attrs((self.attrs[key], val))

            else:

                self.attrs[key] = val


    def __iadd__(self, other):

        self.update_attrs(other)

        return self


    def __iter__(self):

        return iteritems(self.attrs)


    def serialize(self, **kwargs):
        """
        Generates a JSON string with the full contents of the attributes,
        without any whitespace or line break.

        Returns:
            (str): The attributes JSON serialized.
        """

        return self._serialize(self.attrs, **kwargs)


    @classmethod
    def _serialize(
            cls,
            attrs,
            top_key_prefix = False,
            prefix_sep = '_',
            **kwargs
        ):

        if not attrs:

            return ''

        param = {
            'indent': None,
            'separators' (',', ':'),
        }

        param.update(kwargs)

        if top_key_prefix:

            attrs = dict(
                itertools.chain(
                    *(
                        cls._add_prefix(val, top_key, sep = prefix_sep)
                        for top_key, val in iteritems(attrs)
                    )
                )
            )

        return json.dumps(attrs, **param)


    @staticmethod
    def _add_prefix(d, prefix, sep = '_'):

        return dict(
            (
                '%s%s%s' % (prefix, sep, key),
                val
            )
            for key, val in iteritems(d)
        )


    def __str__(self):

        return self.serialize()


    def __len__(self):

        return len(self.attrs)
