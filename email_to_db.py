#!/usr/bin/env python

"""
This script processes incoming emails and enters the appropriate information
into the notifications database.
"""

__author__ = "hausrath@gmail.com (Nate Hausrath)"

import os, sys, time
import re
import email
import uuid
import StringIO
import datetime
import hunting

from vtmis.utilities import *
from vtmis.scoring import *

try:
    import local_settings as settings
except ImportError:
    raise SystemExit('local_settings.py was not found or was not accessible.')

scoring = get_scoring_dict()

# These are new incoming emails
if not os.path.exists(settings.INCOMING_DIR):
    print "There is no incoming email directory!"
    exit(1)
# This is where archived emails go that have already by processed
if not os.path.exists(settings.PROCESSED_EMAIL_DIR):
    os.mkdir(settings.PROCESSED_EMAIL_DIR)
# This is where raw messages for Alertweb go
if not os.path.exists(settings.RAW_MSG_DIR):
    os.mkdir(settings.RAW_MSG_DIR)
# Limit for the number of emails to process this time. Mainly used for testing.
# Set to 0 for unlimited.
LIMIT = 0

# Build our regex strings
re_md5 = re.compile(r'MD5\s+:\s+([A-Fa-f0-9]{32})')
re_sha1 = re.compile(r'SHA1\s+:\s+([A-Fa-f0-9]{40})')
re_sha256 = re.compile(r'SHA256\s+:')
re_type = re.compile(r'Type\s+:\s+([A-Za-z0-9\s]+)')
re_orig_filename = re.compile(r'OriginalFilename\s+:\s+([\w\s\d]+)')
re_link = re.compile(r'Link\s+:')
re_rule = re.compile('\[VTMIS\]\[[a-f0-9]+\]\s(.*)$')
re_first_country = re.compile(r'First country\s*:\s+([A-Za-z]{2})')
re_first_source = re.compile(r'First source\s+:\s+([a-z0-9]{8})\s+\(([a-z0-9A-Z]+)\)')

incoming_count = len(os.listdir(settings.INCOMING_DIR))
total_processed = 0

for f in os.listdir(settings.INCOMING_DIR):
    if os.path.isdir(settings.INCOMING_DIR + "/" + f):
        continue
    if LIMIT > 0 and total_processed >= LIMIT:
        continue
    if total_processed % 100 == 0:
        # TODO: This will not complete if the number of emails is too small.
        print "Processed " + str(total_processed) + " / " + str(incoming_count)
    total_processed += 1

    # Read our email
    fin = open(settings.INCOMING_DIR + "/" + f, 'r')
    fstr = fin.read()
    fin.close()

    msg = email.message_from_string(fstr)

    rule = ''
    md5 = ''
    sha1 = ''
    sha256 = ''
    filetype = ''
    orig_file_name = ''
    link = ''
    first_source = ''
    first_source_type = ''
    first_country = ''

    # Get and clean the subject
    subject = ''.join(str(msg['subject']).splitlines())
    re_rule = re.compile(r'\[VTMIS\]\[[0-9A-Za-z]+\]\s*(.*)')
    re_rule_match = re_rule.search(subject.split(":")[0])
    if re_rule_match:
        rule = re_rule_match.group(1)
    else:
        print "Cannot find the appropriate rule match in the email subject, failing."
        exit(1)

    payload = StringIO.StringIO(msg.get_payload())
    next_sha256 = False
    next_link = False
    raw_msg_text = ""
    raw_msg_file = str(uuid.uuid4())

    maintype = msg.get_content_maintype()
    if maintype == 'text':
        for line in payload.readlines():
            raw_msg_text = raw_msg_text + line
            match_md5 = re_md5.search(line)
            match_sha1 = re_sha1.search(line)
            match_sha256 = re_sha256.search(line)
            match_type = re_type.match(line)
            match_orig_fname = re_orig_filename.search(line)
            match_first_source = re_first_source.search(line)
            match_first_country = re_first_country.search(line)
            # Some goofy logic here to handle multilines and whatnot.
            if next_sha256:
                sha256 = line.rstrip()
                next_sha256 = False
            if match_md5:
                md5 = match_md5.group(1)
            if match_sha1:
                sha1 = match_sha1.group(1)
            if match_sha256:
                next_sha256 = True
            if match_type:
                filetype = match_type.group(1)
                filetype = filetype.rstrip()
            if match_orig_fname:
                orig_file_name = match_orig_fname.group(1)
            if match_first_source:
                first_source = match_first_source.group(1)
                first_source_type = match_first_source.group(2)
            if match_first_country:
                first_country = match_first_country.group(1)
                
        # Get time for file paths
        utctime = time.gmtime()
        utctimestr = time.strftime("%Y-%m-%d", utctime)

        # Build our file locations
        email_archive = utctimestr + "/" + f
        raw_email_html = utctimestr + "/" + f

        # Get the timestamp
        created_at = datetime.datetime.now()

        # First check to see if this file and rule hits are already in the database.
        check_exists = hunting.sess.query(hunting.Hit).filter(hunting.Hit.md5 == md5, hunting.Hit.rule == rule).first()

        if check_exists is None:
            # Check if a download exists for this md5 already
            dl = hunting.sess.query(hunting.Download).filter(hunting.Download.md5 == md5).first()
            if dl is None:
                dl = hunting.Download(md5=md5, sha1=sha1, score=0, process_state=0)
            # Now we write all the data we scraped to the DB
            hit = hunting.Hit(md5=md5, sha1=sha1, sha256=sha256, rule=rule, processed=0, created_at=created_at, first_source=first_source, first_country=first_country, file_type=filetype, first_source_type=first_source_type, orig_file_name=orig_file_name, raw_email_html=raw_email_html, email_archive=email_archive, score=get_string_score(rule), download=dl)
            dl.score += hit.score
            hunting.sess.add(hit)
            hunting.sess.commit()

        # Convert the raw message to html and write it out
        # This file will get attached to the alertweb alert as part of the details
        # page
        if not os.path.exists(settings.RAW_MSG_DIR + "/" + utctimestr):
            os.mkdir(settings.RAW_MSG_DIR + "/" + utctimestr)
        if not os.path.exists(settings.PROCESSED_EMAIL_DIR + "/" + utctimestr):
            os.mkdir(settings.PROCESSED_EMAIL_DIR + "/" + utctimestr)
        raw_msg_html = convert_msg_to_html(raw_msg_text)
        fout = open(settings.RAW_MSG_DIR + raw_email_html, "w")
        fout.write(raw_msg_html)
        fout.close()
        os.rename(settings.INCOMING_DIR + f, settings.PROCESSED_EMAIL_DIR + email_archive)