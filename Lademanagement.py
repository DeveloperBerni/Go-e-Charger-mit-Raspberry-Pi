#!/usr/bin/python3

import os
import threading
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
import time
from datetime import datetime
import tkinter
from tkinter import *

#Global tags:
global exitFlag
global vorOrt, conect
#Im weiteren Programm steht N für Netzbedarf und S für Solarstrom.
global N1, N2, N3
global S1, S2, S3
global Strom, Lsoll, Frg, Send_ok, Send_fail
exitFlag, vorOrt, conect = 0, 0, 0
S1, S2, S3 = 0, 0, 0
N1, N2, N3 = 0, 0, 0
Strom, Lsoll, Frg, Send_ok, Send_fail = 0, 0, 0, 0, 0

GPIO.setwarnings(False)
GPIO.setup(4, GPIO.OUT)  #Livebit LED zur Anzeige dass das Programm noch läuft
GPIO.setup(17, GPIO.IN)
GPIO.setup(18, GPIO.IN)
GPIO.setup(22, GPIO.IN)
GPIO.setup(23, GPIO.IN)
GPIO.setup(24, GPIO.IN)
GPIO.setup(27, GPIO.IN)

#Threads
class messen(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
    def run(self):
        #print("\nStarting " + self.name)
        msec_act = datetime.now().microsecond
        msec_old = 0
        global N1, N2, N3
        global S1, S2, S3
        global Sendung, Send_ok, Send_fail
        Run1N, Run2N, Run3N = 0.0, 0.0, 0.0
        Run1S, Run2S, Run3S = 0.0, 0.0, 0.0
        Bit1N, Bit2N, Bit3N = 0, 0, 0
        Bit1S, Bit2S, Bit3S = 0, 0, 0
        E_N, E_S, E_Ntag, E_Stag = 0.0, 0.0, 0.0, 0.0  # Energiezähler in kWh
        Stunde = datetime.now().hour
        #print (str(datetime.now()) + "   Überschuss Solar: " + str(E_Stag) +"  Netzbedarf: " + str(E_Ntag) +"kWh \n")

        while True:
            time.sleep(0.01)
            #Ermittlung der Cykluszeit im Millisekunden
            msec_old = msec_act
            msec_act = datetime.now().microsecond
            cycle = (msec_act - msec_old) / 1000
            if msec_act < msec_old:
                cycle= (msec_act - msec_old + 1000000) / 1000

            N1, E_N, Run1N, Bit1N = getWatt(N1, E_N, Run1N, Bit1N, 17, cycle)
            N2, E_N, Run2N, Bit2N = getWatt(N2, E_N, Run2N, Bit2N, 18, cycle)
            N3, E_N, Run3N, Bit3N = getWatt(N3, E_N, Run3N, Bit3N, 27, cycle)
            S1, E_S, Run1S, Bit1S = getWatt(S1, E_S, Run1S, Bit1S, 22, cycle)
            S2, E_S, Run2S, Bit2S = getWatt(S2, E_S, Run2S, Bit2S, 23, cycle)
            S3, E_S, Run3S, Bit3S = getWatt(S3, E_S, Run3S, Bit3S, 24, cycle)
            #Ermittlung des Überhanges pro Stunde
            if Stunde != datetime.now().hour: #!= ist ungleich
                E_S = round(E_S/100) / 10 #Erzeugte Solarenergie
                E_N = round(E_N/100) / 10 #Verbrauchte Netzleistung
                if E_N > E_S:
                    E_Ntag = E_Ntag + E_N - E_S #Tagessumme Netzleistung
                else:
                    E_Stag = E_Stag + E_S - E_N #Tagessumme PV Einspeisung
                Stunde = datetime.now().hour
                E_N, E_S = 0.0, 0.0

                if Stunde == 8: #Printausgabe um 8:00 Uhr
                    print (str(datetime.now()) + "   Überschuss Solar: " + str(E_Stag) +"  Netzbedarf: " + str(E_Ntag) +"kWh")
                    E_Ntag, E_Stag = 0.0, 0.0
                    Send_ok, Send_fail = 0, 0
                    print ("Fehlerspeicher: "+ str(Send_ok) +" / "+ str(Send_fail))

            if msec_act < 500000:             #Life Bit 1Hz
                GPIO.output(4, GPIO.HIGH)     #LED am GPIO angeschlossen als "RUN" Anzeige
            else:
                GPIO.output(4, GPIO.LOW)
            if exitFlag:
                break

        #print("Exiting " + self.name)

def getWatt(watt, wattH, runtime, flag, io, cycle):
    Leistung, Energie, Laufzeit, Bit = watt, wattH, runtime, flag
    if GPIO.input(io) == 0 and Laufzeit < 361000:
        Laufzeit = Laufzeit + cycle
        Bit = 0
    else:
        if Bit == 0:
            if Laufzeit >= 0.1: #in Millisekunden
                Laufzeit = Laufzeit / 1000 #in Sekunden

                #Ist die Laufzeit > 360 Sekunden ergibt sich eine Leistung von < 5.
                #Für die Messung ist diese Geringe Leistung irrelevant
                #und wird somit auf 0 gesetzt.
                if Laufzeit > 360:
                    Leistung = 0
                else:
                    Leistung = round(1800 / Laufzeit)
                    Energie = Energie + 0.5
                Laufzeit = 0
                Bit = 1
        else:
            Laufzeit = Laufzeit + cycle
    return Leistung, Energie, Laufzeit, Bit

#Go-eCharger steuern
class Goe(threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
    def run(self):
        #import requests
        #from requests.exceptions import Timeout
        from threading import Thread

        #print("\nStarting " + self.name)
        global N1, N2, N3
        global S1, S2, S3
        global conect, vorOrt, Send_ok, Send_fail
        global Strom, Lsoll, Frg
        Frg, Frg_last, Strom_last = 0, 9, 99
        Frg_send, Strom_send = 0, 0
        Lslv = 0   #Leistung Schieflastverordnung

        def Send(api,value):
            import requests
            from requests.exceptions import Timeout
            global conect
            hostname = "http://go-eCharger.fritz.box/mqtt?payload"
            url = hostname + api + str(value)
            try:
                r = requests.get(url, timeout=3)
                #print(r.url)
            except Timeout:
                conect = 0 #keine Verbindung
            else:
                conect = 1 #Verbindung OK
            time.sleep(3.5)

        while True:
            # Ermittlen Stromstärke für Go-eCahrger - angeschlossen auf Phase L3
            time.sleep(0.1)
            if N1 >  N2:                           #4650W Schieflastverordnung
                Lslv = round(4650 + N2 - N3)
            else:
                Lslv = round(4650 + N1 - N3)
            if Lslv <= 0:
                Lslv = 0
            #maximle verfügbare Ladeleistung, abzüglich 200W Hausgrundversorgung
            Lmax = round((S1 + S2 + S3) - (N1 + N2 + N3) - 200)
            if Lmax <= 0:
                Lmax = 0

            if Lslv > Lmax:
                Lsoll = Lmax
            else:
                Lsoll = Lslv

            Strom_soll = round((Lsoll + 10) / 230)
            #Einstellung maximaler Ladestrom abhängig von der Sicherung
            if Strom_soll > 20:
                Strom_soll = 20

            if Strom_soll < 6:
                Strom_soll = 6
                Frg_soll = 0
            else:
                Frg_soll = 1
            if vorOrt == 1:
                Frg_soll = 1
            Frg = Frg_soll
            Strom = Strom_soll
            #print("Lsoll: " + str(Lsoll) + "    Strom: " + str(Strom))
            #print("Freigabe: "+str(Send_Frg) +"   VorOrt: " +str(vorOrt))

            #write to go-e
            if Frg != Frg_last or Frg_send > 0:
                Frg_last = Frg
                t = Thread(target=Send, args=("=alw=",Frg))
                t.start()
                time.sleep(4)
                if conect:
                    Send_ok = Send_ok + 1
                    Frg_send = 0
                else:
                    Send_fail = Send_fail + 1
                    Frg_send = Frg_send + 1
                    print(str(datetime.now()) +" Send Freigabe Fehler("+str(Frg)+"):"+str(Frg_send))
                if Frg_send > 4:
                    Frg_send = 0

            if vorOrt == 0 and Strom != Strom_last or Strom_send > 0:
                Strom_last = Strom
                t = Thread(target=Send, args=("=amp=",Strom))
                t.start()
                time.sleep(4)
                if conect:
                    Send_ok = Send_ok + 1
                    Strom_send = 0
                else:
                    Send_fail = Send_fail + 1
                    Strom_send = Strom_send + 1
                    print(str(datetime.now()) +" Send Strom Fehler("+str(Strom)+"A):"+str(Strom_send))
                if Strom_send > 4:
                    Strom_send = 0

            if exitFlag:
                break


#GUI Anzeige im Display
class myGUI (threading.Thread):
    def __init__(self, threadID, name):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name

    def run(self):

        root = Tk() #Fenseter erstellen
        root.wm_title("aktuelle Verbrauchswerte") #Fenster Titel
        root.config(background = "#006699") #Hintergrundfarbe

        #Funktionen festlegen
        def refresh():
            global vorOrt, Frg, conect
            AnzS1.set("Solarpower L1: " + str(S1) + "W")
            AnzS2.set("Solarpower L2: " + str(S2) + "W")
            AnzS3.set("Solarpower L3: " + str(S3) + "W")
            AnzSges.set("Solarpower : " + str(round((S1+S2+S3)/10)/100) + "kW")

            AnzN1.set("Verbrauch L1: " + str(N1) + "W")
            AnzN2.set("Verbrauch L2: " + str(N2) + "W")
            AnzN3.set("Verbrauch L3: " + str(N3) + "W")
            AnzNges.set("Verbrauch : " + str(round((N1+N2+N3)/10)/100) + "kW")
            if vorOrt == 0:
                SelectControl.set("PV-Anl. (" + str(Strom) +"A/" + str(Lsoll) +"W/ Frg. "+str(Frg)+")")
            else:
                SelectControl.set("Wallb. (" + str(Strom) +"A/" + str(Lsoll) +"W/ Frg. "+str(Frg)+")")

            if conect == 0:
                ConText.set("Telegramm: ("+str(Send_ok)+"/"+str(Send_fail)+") *Fehler*")
            else:
                ConText.set("Telegramm: ("+str(Send_ok)+"/"+str(Send_fail)+") *OK*")

            root.after(1000, refresh) #GUI wird einmal pro Sekunde upgedatet

        def killmess():
            global exitFlag
            exitFlag = 1
            #print("Manueller Abbruch " + str(exitFlag))

        def newstart():
            global exitFlag
            exitFlag = 1
            #print("Manueller Abbruch und Reboot " + str(exitFlag))
            time.sleep(10)
            os.system("sudo reboot")

        def location():
            global vorOrt
            if vorOrt == 0:
                vorOrt = 1
            else:
                vorOrt = 0

        #Ab hier Elemente einfügen
        leftFrame = Frame(root, width=400, height=240)
        leftFrame.grid(row=0, column=0, padx=5, pady=3)

        rightFrame = Frame(root, width=400, height=240)
        rightFrame.grid(row=0, column=1, padx=5, pady=3)

        AnzS1 = StringVar()
        AnzS2 = StringVar()
        AnzS3 = StringVar()
        AnzSges = StringVar()
        AnzN1 = StringVar()
        AnzN2 = StringVar()
        AnzN3 = StringVar()
        AnzNges = StringVar()
        SelectControl = StringVar()
        ConText = StringVar()

        varFrame = Frame(leftFrame)
        varFrame.grid(row=0, column=0, padx=10, pady=3)
        lS1 = Label(varFrame, width=20, height=1, relief = RAISED, font=("Times","20","bold"), textvariable = AnzS1)
        lS1.grid(row=0, column=0, padx=2, pady=1)
        lS2 = Label(varFrame, width=20, height=1, relief = RAISED, font=("Times","20","bold"), textvariable = AnzS2)
        lS2.grid(row=1, column=0, padx=2, pady=1)
        lS3 = Label(varFrame, width=20, height=1, relief = RAISED, font=("Times","20","bold"), textvariable = AnzS3)
        lS3.grid(row=2, column=0, padx=2, pady=1)
        lSges = Label(varFrame, width=20, height=2, relief= RAISED, font=("Times","20","bold"), textvariable= AnzSges)
        lSges.grid(row=3, column=0, padx=2, pady=5)

        lN1 = Label(varFrame, width=20, height=1, relief = RAISED, font=("Times","20","bold"), textvariable = AnzN1)
        lN1.grid(row=0, column=1, padx=5, pady=1)
        lN2 = Label(varFrame, width=20, height=1, relief = RAISED, font=("Times","20","bold"), textvariable = AnzN2)
        lN2.grid(row=1, column=1, padx=5, pady=1)
        lN3 = Label(varFrame, width=20, height=1, relief = RAISED, font=("Times","20","bold"), textvariable = AnzN3)
        lN3.grid(row=2, column=1, padx=5, pady=1)
        lNges = Label(varFrame, width=20, height=2, relief= RAISED, font=("Times","20","bold"), textvariable= AnzNges)
        lNges.grid(row=3, column=1, padx=5, pady=5)

        buttonFrame1 = Frame(rightFrame)
        buttonFrame1.grid(row=1, column=1, padx=1, pady=3)

        B1 = Button(buttonFrame1, text="Stop Messung", bg="#FFFF00", width=15, font=("Times","16","bold"), command=killmess)
        B1.grid(row=1, column=0, padx=2, pady=2)
        B2 = Button(buttonFrame1, text="Reboot", bg="#FFA000", width=15, font=("Times","16","bold"), command=newstart)
        B2.grid(row=1, column=1, padx=5, pady=2)

        buttonFrame2 = Frame(rightFrame)
        buttonFrame2.grid(row=2, column=1, padx=1, pady=2)

        Tx1 = Label(buttonFrame2, width=25, height=1, font=("Times","16","bold"), textvariable= ConText)
        Tx1.grid(row=2, column=0, padx=5, pady=5)
        Tx2 = Label(buttonFrame2, width=25, height=1, font=("Times","14","bold"), text= ("Aktuelle Bedienhoheit:"))
        Tx2.grid(row=3, column=0, padx=5, pady=5)
        BSelect = Button(buttonFrame2, textvariable= SelectControl, bg= "#00FFA0", width=24, font=("Times","24","bold"), command=location)
        BSelect.grid(row=4, column=0, padx=10, pady=3)

        root.after(1000, refresh) #GUI wird das erste mal upgedatet
        root.mainloop()
        #print ("Exiting " + self.name)

thread1 = messen(1, "Datenerfassung")
thread2 = Goe(2, "Go-e steuern")
thread3 = myGUI(3, "GUI")

# Start new Threads
thread1.start()
thread2.start()
thread3.start()
thread1.join()
thread2.join()
thread3.join()
time.sleep(0.5)
