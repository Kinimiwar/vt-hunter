#!/usr/bin/env python
import curses
import hunting
import email

from vtmis.scoring import *

try:        
    import local_settings as settings
except ImportError:
    raise SystemExit('local_settings.py was not found or was not accessible.')

def display_normal(stdscr, dl):
    # Get the rule 'tags'
    hits = hunting.sess.query(hunting.Hit).filter(hunting.Hit.download == dl).all()
    rtags = []
    ctags = []
    file_type = ""
    first_country = ""
    for hit in hits:
        rtags.extend(hit.rule.split("_"))
        file_type = hit.file_type
        first_country = hit.first_country
        ctags.append(get_rule_campaign(hit.rule))
    campaigns = set(ctags)
    rule_tags = set(rtags)

    # Display them
    stdscr.addstr(3,1,"Rule hits: {0}".format(",".join(rule_tags)))
    stdscr.addstr(4,1,"Score: {0}".format(dl.score))
    stdscr.addstr(5,1,"Campaign Matches: {0}".format(" - ".join(campaigns)))
    stdscr.addstr(6,1,"File Type: {0}".format(file_type))
    stdscr.addstr(7,1,"First Country: {0}".format(first_country))

def display_raw(stdscr, dl):
    # Display more information about the email
    # TODO: Allow for more than just the first raw email hit (allow cycling)
    first_hit = hunting.sess.query(hunting.Hit).filter(hunting.Hit.download == dl).first()
    # Figure out how many lines we have available to display this text
    lines_available = stdscr.getmaxyx()[0] - 8
    if lines_available < 0:
        return

    fin = open(settings.RAW_MSG_DIR + first_hit.raw_email_html, "r")
    text = fin.read().split('<br />')
    fin.close()
    line_num = 1
    for line in text:
        line = line.replace("<br />", "")
        if line_num > lines_available:
            continue
        # Start printing on line 3 (line_num + 2)
        stdscr.addstr(line_num + 2,2,line)
        line_num += 1

def main():
    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(1)
    
    curses.start_color()
    scrsize = stdscr.getmaxyx()

    # Init some fancy colors
    curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)

    dl_queue = hunting.sess.query(hunting.Download).filter(hunting.Download.process_state == 0).all()
    dl_iter = iter(dl_queue)
    current_dl = dl_iter.next()

    running = True
    toggle_raw = False
    while running:
        stdscr.clear()
        stdscr.addstr(1,1,"VT HUNTER V0.00001", curses.A_BOLD)

        if current_dl is None:
            stdscr.addstr(3,1,"No alerts are available for review!", curses.A_BOLD)
        else:
            if toggle_raw:
                display_raw(stdscr, current_dl)
            else:
                display_normal(stdscr, current_dl)

        # Display Help
        stdscr.addstr(scrsize[0] - 4, 1, "COMMANDS", curses.color_pair(1))
        stdscr.addstr(scrsize[0] - 3, 1, "q - quit    r - raw email    d - download", curses.color_pair(1))
        stdscr.addstr(scrsize[0] - 2, 1, "s - skip", curses.color_pair(1))
                
        c = stdscr.getch()
        # Toggle commands
        commands = []
        if c == ord('q'):
            commands.extend('q')
        if current_dl is not None:
            if c == ord('s'):
                commands.extend('s')
            if c == ord('r'):
                commands.extend('r')
            if c == ord('d'):
                commands.extend('d')
                commands.extend('s')

        # Process commands
        if 'q' in commands:
            running = False
            break
        if 'd' in commands:
            # 1 = Download
            current_dl.process_state = 1
            hunting.sess.commit()
        if 's' in commands:
            toggle_raw = False
            try:
                current_dl = dl_iter.next()
            except StopIteration:
                dl_queue = hunting.sess.query(hunting.Download).filter(hunting.Download.process_state == 0).all()
                if len(dl_queue) < 1:
                    current_dl = None
                else:
                    dl_iter = iter(dl_queue)
                    current_dl = dl_iter.next()
        if 'r' in commands:
            if toggle_raw:
                toggle_raw = False
            else:
                toggle_raw = True

    # Wrap it up and return the console to normal.
    curses.nocbreak(); stdscr.keypad(0); curses.echo()
    curses.endwin()

if __name__ == "__main__":
    main()