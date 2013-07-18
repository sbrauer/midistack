#!/usr/bin/env python

# A utility for creating "midi stacks" under ALSA (Linux).
# A midi stack is a set of midi output/channel pairs that the same
# midi events are sent to.  This allows a user to play multiple patches
# possibly on multiple synths possibly on multiple midi connections
# as if they were one instrument: a stack of synths for complex layered timbres!
# by Sam Brauer (2013)

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pyseq
import sys
import json
import pprint

NUM_OUTS = 4
NUM_SLOTS = 4
MIDI_CHANNELS = 16
SEMITONE_RANGE = 24

class Slot():

    def __init__(self):
        self.enabled = False
        self.output = 0
        self.channel = 0
        self.notes = [0]

    def to_dict(self):
        return dict(
            enabled = self.enabled,
            output = self.output,
            channel = self.channel,
            notes = self.notes,
        )

class StackSeq(pyseq.PySeq):

    def init(self, *args):
        self.in_port = self.createInPort()
        self.out_ports = []
        for x in range(NUM_OUTS):
            self.out_ports.append(self.createOutPort())
        self.init_stacks()

    def init_stacks(self):
        self.stacks = []
        for ch in range(MIDI_CHANNELS):
            stack = []
            self.stacks.append(stack)
            for s in range(NUM_SLOTS):
                stack.append(Slot())

    def callback(self, ev):
        if ev.type not in (
            pyseq.SND_SEQ_EVENT_NOTE,
            pyseq.SND_SEQ_EVENT_NOTEON,
            pyseq.SND_SEQ_EVENT_NOTEOFF,
            pyseq.SND_SEQ_EVENT_CONTROLLER,
            pyseq.SND_SEQ_EVENT_PITCHBEND,
        ):
            return 1
        data = ev.getData()
        orig_note = None
        is_note_event = ev.type in (pyseq.SND_SEQ_EVENT_NOTE, pyseq.SND_SEQ_EVENT_NOTEON, pyseq.SND_SEQ_EVENT_NOTEOFF)
        if is_note_event:
            orig_note = data.note
        for slot in self.stacks[data.channel]:
            if slot.enabled:
                data.channel = slot.channel
                if is_note_event:
                    for note in slot.notes:
                        data.note = orig_note + note
                        if (data.note > -1) and (data.note < 128):
                            ev.setData(data)
                            ev.sendNow(self, self.out_ports[slot.output])
                else:
                    ev.setData(data)
                    ev.sendNow(self, self.out_ports[slot.output])
        return 1

    def set_enabled(self, ch_in, slot, val):
        # ch_in and slot are 0-based indexes
        # val is a boolean
        self.stacks[ch_in][slot].enabled = val

    def set_output(self, ch_in, slot, val):
        # ch_in and slot are 0-based indexes
        # val is an int identifying an output by index
        self.stacks[ch_in][slot].output = val

    def set_channel(self, ch_in, slot, val):
        # ch_in and slot are 0-based indexes
        # val is an int identifying an output channel by index
        self.stacks[ch_in][slot].channel = val

    def add_note(self, ch_in, slot, val):
        # ch_in and slot are 0-based indexes
        # val is a signed ints representing a semitone offset
        notes = self.stacks[ch_in][slot].notes
        if val not in notes:
            notes.append(val)

    def del_note(self, ch_in, slot, val):
        # ch_in and slot are 0-based indexes
        # val is a signed ints representing a semitone offset
        notes = self.stacks[ch_in][slot].notes
        if val in notes:
            notes.remove(val)

    def serialize(self):
        return [ [ slot.to_dict() for slot in stack ] for stack in self.stacks ]

class MidiStack:
    def __init__(self):
        self.filename = None

        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window = window
        window.set_title("MidiStack")
        window.set_size_request(805, 520)
        #window.set_resizable(False)
        window.set_position(1)
        window.connect("delete_event", self.delete_event)

        box = gtk.VBox(False, 0)
        window.add(box)

        menubar = gtk.MenuBar()
        box.pack_start(menubar, False, False, 0)

        menu = gtk.Menu()
        item = gtk.MenuItem("File")
        item.set_submenu(menu)
        menubar.append(item)

        item = gtk.MenuItem("Open...")
        item.connect("activate", self.load_kit_callback)
        menu.append(item)

        item = gtk.MenuItem("Reload")
        item.connect("activate", self.reload_kit_callback)
        item.set_sensitive(False)  # Only sensitive (aka "enabled") if self.filename
        self.reload_btn = item
        menu.append(item)

        item = gtk.MenuItem("Save")
        item.connect("activate", self.save_kit_callback)
        item.set_sensitive(False)  # Only sensitive (aka "enabled") if self.filename
        self.save_btn = item
        menu.append(item)

        item = gtk.MenuItem("Save as...")
        item.connect("activate", self.save_kit_as_callback)
        menu.append(item)

# FIXME: implement
#        item = gtk.MenuItem("Init")
#        item.connect("activate", self.init_kit_callback)
#        menu.append(item)

# FIXME: implement
#        item = gtk.MenuItem("Panic")
#        item.connect("activate", self.panic_callback)
#        menu.append(item)

# FIXME: delete this and debug() ???
        item = gtk.MenuItem("Debug")
        item.connect("activate", self.debug)
        menu.append(item)

        item = gtk.MenuItem("Exit")
        item.connect("activate", self.delete_event)
        menu.append(item)

        table = gtk.Table(MIDI_CHANNELS + 1, NUM_SLOTS + 1)
        table.set_border_width(5)
        box.pack_start(table, True, True, 0)

        label = gtk.Label("Ch")
        table.attach(label, 0, 1, 0, 1, gtk.FILL, 0)
        for slot in range(NUM_SLOTS):
            label = gtk.Label("Slot %d" % (slot+1))
            table.attach(label, slot+1, slot+2, 0, 1, gtk.FILL, 0)

        # A lists of lists that parallels the 16 stacks of slots.
        self.widgets = []

        for channel in range(MIDI_CHANNELS):
            label = gtk.Label("%02d" % (channel+1))
            table.attach(label, 0, 1, channel+1, channel+2, gtk.FILL, xpadding=5)

            channel_widgets = []
            self.widgets.append(channel_widgets)

            for slot in range(NUM_SLOTS):
                box = gtk.HBox(False, 0)
                table.attach(box, slot+1, slot+2, channel+1, channel+2, gtk.FILL, xpadding=5)

                slot_widgets = {}
                channel_widgets.append(slot_widgets)

                widget = gtk.CheckButton()
                widget.channel = channel
                widget.slot = slot
                widget.parameter = 'enabled'
                widget.connect("toggled", self.changed_callback)
                box.pack_start(widget, False, False, 0)
                slot_widgets[widget.parameter] = widget

                widget = gtk.OptionMenu()
                menu = gtk.Menu()
                for output in range(NUM_OUTS):
                    menu.add(gtk.MenuItem(label="out %d" % (output+1)))
                widget.set_menu(menu)
                widget.channel = channel
                widget.slot = slot
                widget.parameter = 'output'
                widget.connect("changed", self.changed_callback)
                box.pack_start(widget, False, False, 0)
                slot_widgets[widget.parameter] = widget

                widget = gtk.OptionMenu()
                menu = gtk.Menu()
                for out_ch in range(MIDI_CHANNELS):
                    menu.add(gtk.MenuItem(label="%02d" % (out_ch+1)))
                widget.set_menu(menu)
                widget.channel = channel
                widget.slot = slot
                widget.parameter = 'channel'
                widget.connect("changed", self.changed_callback)
                box.pack_start(widget, False, False, 0)
                slot_widgets[widget.parameter] = widget

                widget = gtk.OptionMenu()
                menu = gtk.Menu()
                for semi in range(-SEMITONE_RANGE, SEMITONE_RANGE+1):
                    item = gtk.CheckMenuItem(label="%d" % semi)
                    item.set_active(semi == 0)
                    item.note = semi
                    item.connect("toggled", self.note_changed_callback)
                    menu.add(item)
                widget.set_menu(menu)
                widget.set_history(SEMITONE_RANGE)
                box.pack_start(widget, False, False, 0)
                menu.channel = channel
                menu.slot = slot
                menu.parameter = 'notes'
                slot_widgets[menu.parameter] = menu

        self.seq = StackSeq('MidiStack')
        self.thread = pyseq.MidiThread(self.seq)
        self.thread.start()

        if len(sys.argv) > 1:
            fn = sys.argv[1]
            self.set_filename(fn)
            self.load_kit()

        window.show_all()

    def changed_callback(self, widget):
        parm = widget.parameter
        if parm == 'enabled':
            self.seq.set_enabled(widget.channel, widget.slot, widget.get_active())
        elif parm == 'output':
            self.seq.set_output(widget.channel, widget.slot, widget.get_history())
        elif parm == 'channel':
            self.seq.set_channel(widget.channel, widget.slot, widget.get_history())

    def note_changed_callback(self, widget):
        menu = widget.get_parent()
        if widget.get_active():
            self.seq.add_note(menu.channel, menu.slot, widget.note)
        else:
            self.seq.del_note(menu.channel, menu.slot, widget.note)

    def delete_event(self, *args):
        self.thread.stop()
        gtk.main_quit()
        return False

    def debug(self, *args):
        pprint.pprint(self.seq.serialize())

    def save_kit_as_callback(self, ev):
        chooser = gtk.FileChooserDialog(title="Save kit as...", action=gtk.FILE_CHOOSER_ACTION_SAVE, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        response = chooser.run()
        save = False
        if response == gtk.RESPONSE_OK:
            self.set_filename(chooser.get_filename())
            save = True
        chooser.destroy()
        if save: self.save_kit()

    def save_kit_callback(self, ev):
        self.save_kit()

    def save_kit(self):
        try:
            outfile = open(self.filename, 'w')
            outfile.write(json.dumps(self.seq.serialize(), indent=2))
            outfile.close()
        except:
            dialog = gtk.MessageDialog(flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK, message_format="Error saving kit.")
            dialog.run()
            dialog.destroy()

    def load_kit(self):
        try:
            infile = open(self.filename, 'r')
            json_string = infile.read()
            infile.close()
            stacks = json.loads(json_string)

            for (ch, slots) in enumerate(stacks):
                for (slot, slot_dict) in enumerate(slots):
                    self.widgets[ch][slot]['enabled'].set_active(slot_dict['enabled'])
                    self.widgets[ch][slot]['output'].set_history(slot_dict['output'])
                    self.widgets[ch][slot]['channel'].set_history(slot_dict['channel'])
                    slot_notes = slot_dict['notes']
                    for item in self.widgets[ch][slot]['notes'].get_children():
                        item.set_active(item.note in slot_notes)
        except:
            dialog = gtk.MessageDialog(flags = gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK, message_format="Error loading kit.")
            dialog.run()
            dialog.destroy()

    def load_kit_callback(self, ev):
        chooser = gtk.FileChooserDialog(title="Load kit...", action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        response = chooser.run()
        load = False
        if response == gtk.RESPONSE_OK:
            self.set_filename(chooser.get_filename())
            load = True
        chooser.destroy()
        if load: self.load_kit()

    def reload_kit_callback(self, ev):
        self.load_kit()

    def set_filename(self, fn):
        self.filename = fn
        if fn:
            self.window.set_title("MidiStack - %s" % fn)
            self.save_btn.set_sensitive(True)
            self.reload_btn.set_sensitive(True)
        else:
            self.window.set_title("MidiStack")
            self.save_btn.set_sensitive(False)
            self.reload_btn.set_sensitive(False)

def main():
    gobject.threads_init()
    app = MidiStack()
    gtk.main()
    return 0

if __name__ == "__main__":
    main()
