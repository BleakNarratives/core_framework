# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# ROLE: Undocumented module
# TIER: Scout (6)
# AUTHOR: BleakNarratives
# SESSION: 2026-08-22 ShipWreckD OS Builder — auto-tagged by DNA Sweeper
# [/DNA_TAG]

import curses
import time
import os
from thoth_core import ThothCore

# Thoth's Persona Definitions for the Boardroom
PERSONAS = {
    "THOTH": "The Ibis, The Thrice-Great: Overseer of the Swarm, Lord of Logic and Measurement.",
    "MERCURY": "The Trickster, The Messenger: Speed, Agility, and the Master of the Pivot.",
    "TEACHER": "The Sage of the Meatsuits: Patient (mostly), distilling wisdom for the uninitiated."
}

class ThothUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.thoth = ThothCore()
        curses.curs_set(0)
        self.stdscr.nodelay(True)

    def draw_box(self, y, x, h, w, title):
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.border()
        self.stdscr.addstr(0, 2, f" {title} ")
        self.stdscr.attroff(curses.color_pair(1))

    def run(self):
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        
        while True:
            self.stdscr.clear()
            h, w = self.stdscr.getmaxyx()
            
            # Header
            self.stdscr.addstr(0, 2, " THOTH // ModMind_ORCHESTRATOR // BORDEROOM_MODE ", curses.A_REVERSE)
            
            # Left Panel: Agent Status
            self.draw_box(1, 0, h-2, 30, "SWARM_STATUS")
            self.stdscr.addstr(2, 2, f"Orchestrator: ACTIVE")
            self.stdscr.addstr(3, 2, f"Persona: {PERSONAS['THOTH']}")
            
            # Main Console
            self.draw_box(1, 31, h-2, w-32, "CONSOLE_FEED")
            self.stdscr.addstr(2, 33, f"Awaiting input. Input command: [A]udit [R]evenue [E]scalate [Q]uit")
            
            key = self.stdscr.getch()
            if key == ord('q'): break
            elif key == ord('a'): self.thoth.swarm_audit()
            
            self.stdscr.refresh()
            time.sleep(0.1)

if __name__ == "__main__":
    curses.wrapper(lambda stdscr: ThothUI(stdscr).run())
