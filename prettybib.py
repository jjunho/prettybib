#!/usr/bin/env python

"""BibTex checker and formater.

This is a scripts that formats bibtex in a uniform way, orders it by the
authors surnames and checkes the records have all they need.
"""

import sys
import datetime
import re
import argparse

from termcolor import colored
import bibtexparser
from bibtexparser.bwriter import BibTexWriter
import isbnlib
from SPARQLWrapper import SPARQLWrapper, JSON

# pylint: disable=fixme


def log_message(entry, message, color='green'):
    """Print colored log message."""
    sys.stderr.write(colored("{} ({}): {}\n".format(
        entry['ID'], entry['ENTRYTYPE'], message), color=color))


def err_message(entry, message):
    """Print red error message."""
    log_message(entry, message, color='red')


def check_year(entry, _):
    """Check the sanitiy of a year."""
    try:
        year = int(entry['year'])

        current_year = datetime.datetime.now().year

        if year < 0:
            err_message(entry, "year '{}' is negative.".format(year))
        if year > current_year:
            err_message(entry, "year '{}' is in the future.".format(year))
        if year < 1800:
            err_message(entry, "year '{}' is before 1800".format(year))
    except ValueError:
        if entry['year'] != 'TODO':
            err_message(entry,
                        "year '{}' is not an integer".format(entry['year']))


PAGE_REGEX = re.compile(r"^([1-9][0-9]*)[\W_]+([1-9][0-9]*)$")


def check_pages(entry, _):
    """Check range and fix punctuation."""
    pages = entry['pages']
    pages_match = PAGE_REGEX.match(pages)
    if pages_match:
        start, end = pages_match.groups()
        if end < start:
            err_message(entry,
                        "the end page ({}) is before the start page ({})".
                        format(end, start))
    elif pages != 'TODO':
        err_message(entry, "pages field looks strange: '{}'".format(pages))


def check_isbn(entry, try_fix):
    """Check and format ISBN.

    More information about ISBN:
    https://en.wikipedia.org/wiki/International_Standard_Book_Number
    """
    isbn_string = entry['isbn']
    # is_valid_isbn = False
    if isbnlib.is_isbn10(isbn_string):
        # is_valid_isbn = True
        try:
            if int(entry['year']) >= 2007:
                err_message(entry,
                            ("ISBN10 ({}) were issued only before 2007," +
                             " year is actually {}").
                            format(isbn_string, entry['year']))
        # pylint: disable=bare-except
        except:
            pass
    elif isbnlib.is_isbn13(isbn_string):
        # is_valid_isbn = True
        try:
            if int(entry['year']) < 2007:
                err_message(entry,
                            ("ISBN13 ({}) were issued only after 2007," +
                             " year is actually {}").
                            format(isbn_string, entry['year']))
        # pylint: disable=bare-except
        except:
            pass
    else:
        if isbn_string != 'TODO':
            err_message(entry, "Invalid ISBN {}".format(isbn_string))
        # TODO try to look up isbn using isbnlib.goom()
        # intitle:Understanding+inauthor:McLuhan&tbs=,
        #        cdr:1,cd_min:Jan+1_2+1964,cd_max:Dec+31_2+1974&num=10
        return

    if try_fix:
        _fix_based_on_isbn(isbn_string, entry)

    entry['isbn'] = isbnlib.mask(isbn_string)


def _fix_based_on_isbn(isbn_string, entry):
    """Try to find publlisher and year based ISBN."""
    publisher = None
    year = None
    if 'publisher' in entry and entry['publisher'] != 'TODO':
        publisher = entry['publisher']
    if 'year' in entry and entry['year'] != 'TODO':
        year = entry['year']

    try:
        if not publisher or not year:
            meta_data = isbnlib.meta(isbn_string)

            if 'Year' in meta_data and entry['year'] == 'TODO':
                entry['year'] = meta_data['Year']
                log_message(entry, "year found based on ISBN: {}".
                            format(meta_data['Year']))
            if 'Publisher' in meta_data and entry['publisher'] == 'TODO':
                entry['publisher'] = meta_data['Publisher']
                log_message(entry, "publisher found based on ISBN: '{}'".
                            format(meta_data['Publisher']))
    # pylint: disable=bare-except
    except:
        pass
    # pylint: enable=bare-except


ISSN_REGEX = re.compile(r"^\d{4}-?\d{3}[\dxX]$")


def check_issn(entry, try_fix):
    """Check ISSN number."""
    issn_str = entry['issn']
    if ISSN_REGEX.match(issn_str):
        pass
        # TODO get journal infomation and check
    else:
        if issn_str != 'TODO':
            err_message(entry, "Ivalid ISSN format ({}).")

        if 'journal' in entry and try_fix:
            journal = entry['journal']

            sparql = SPARQLWrapper("http://dbpedia.org/sparql")
            sparql.setReturnFormat(JSON)
            sparql.setQuery("""
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX type: <http://dbpedia.org/ontology/>
                SELECT ?journal ?issn
                WHERE {{
                         ?journal a type:AcademicJournal ;
                         rdfs:label ?journal_name ;
                         dbo:issn ?issn .
                         FILTER(str(?journal_name)="{}")
            }}""".format(journal))
            results = sparql.query().convert()
            if results['results']['bindings']:
                issn = results['results']['bindings'][0]['issn']['value']
                entry['issn'] = issn
                log_message(entry, "ISSN for '{}' found: {}".
                            format(journal, issn))
            else:
                err_message(entry, "ISSN for '{}' not found.".format(journal))

    # TODO check address in dbpedia

    # PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    # PREFIX type: <http://dbpedia.org/ontology/>
    # PREFIX prop: <http://dbpedia.org/property/>
    # SELECT ?name
    # WHERE {
    #    ?city a type:Settlement ;
    #    rdfs:label ?name ;
    #    dbo:country ?country.
    #    ?country rdfs:label ?country_name .
    #    FILTER(str(?name) = "Prague") .
    #    FILTER(langMatches(lang(?name),"EN")) .
    #    FILTER(str(?country_name) = "Czech Republic")
    # }


FIELD_CHECKS = {
    'year': check_year,
    'pages': check_pages,
    'isbn': check_isbn,
    'issn': check_issn
}


def check_field(entry, field, try_fix):
    """Check if a field in in the entry, if not add a TODO."""
    if field not in entry or entry[field] == 'TODO':
        entry[field] = 'TODO'
        err_message(entry, "Missing field '{}'".format(field))
    else:
        if field in FIELD_CHECKS:
            FIELD_CHECKS[field](entry, try_fix)


def check_article(entry, try_fix):
    """Check and fix article entries."""
    if 'journal' not in entry:
        err_message(entry, "Journal title is missing.")
        # TODO try to recover from ISSN or paper name
    else:
        journal = entry['journal']

        if journal == 'CoRR' or journal.startswith('arXiv'):
            entry['journal'] = 'arXiv.org'
            entry['issn'] = '2331-8422'
            check_field(entry, 'link', try_fix)
            check_field(entry, 'volume', try_fix)
            # TODO check whether link and volume agree
        else:
            check_field(entry, 'issn', try_fix)
            check_field(entry, 'issue', try_fix)
            check_field(entry, 'pages', try_fix)
            check_field(entry, 'publisher', try_fix)
            check_field(entry, 'address', try_fix)


def check_book(entry, try_fix):
    """Check and fix book entries."""
    check_field(entry, 'publisher', try_fix)
    check_field(entry, 'year', try_fix)
    check_field(entry, 'isbn', try_fix)


def check_inproceedings(entry, try_fix):
    """Check and fix inproceedings entries."""
    check_field(entry, 'booktitle', try_fix)
    check_field(entry, 'month', try_fix)
    check_field(entry, 'year', try_fix)
    check_field(entry, 'address', try_fix)
    check_field(entry, 'pages', try_fix)
    check_field(entry, 'publisher', try_fix)


ENTRY_CHECKS = {
    'article': check_article,
    'inproceedings': check_inproceedings,
    'book': check_book
}


def check_database(database, try_fix):
    """Check the database entries.

    Goes through the bib database and checks if everyting is
    as it shoudl be.
    """
    for entry in database.entries:
        # normalize the vaues
        for key, value in entry.items():
            entry[key] = re.sub(r"\s+", " ", value)

        check_field(entry, 'author', try_fix)
        check_field(entry, 'title', try_fix)

        entry_type = entry['ENTRYTYPE']
        if entry_type in ENTRY_CHECKS:
            ENTRY_CHECKS[entry_type](entry, try_fix)


def main():
    """Main function of the script.

    Loads the bib file, does the chcecking on it and prints out
    sorted and formated database.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=argparse.FileType('r'),
                        default=sys.stdin,
                        help="Input file, default is stdin.")
    parser.add_argument("--output", type=argparse.FileType('w'), default=None,
                        help="Optional output file.")
    parser.add_argument("--try-fix", type=bool, default=False,
                        help="Flag to search information to fix the dtabase.")
    args = parser.parse_args()

    bib_database = bibtexparser.load(args.input)
    check_database(bib_database, args.try_fix)

    if args.output:
        writer = BibTexWriter()
        writer.indent = '    '
        writer.order_by = ['author', 'year', 'title']
        writer.align_values = True
        args.output.write(writer.write(bib_database))


if __name__ == "__main__":
    main()
