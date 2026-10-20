#!/usr/bin/env python3
"""MaMoyenne : choisissez votre niveau, ajoutez vos matières, la moyenne se met à jour."""
import csv
import os
import re
import sqlite3
import sys
import tkinter as tk
import tkinter.font as tkfont
from datetime import date
from pathlib import Path
from tkinter import filedialog, ttk

NOM_APP = "MaMoyenne"
ANCIEN_NOM_APP = "CalculMoyenne"  # dossier de données avant le changement de nom
NIVEAUX = {"L1": 70, "L2": 70, "L3": 75, "L4": 80}  # niveau -> note de passage
COEF_DEFAUT = 100
NOTE_MAX = 100
VERT, ROUGE, GRIS = "#1a7f37", "#c62828", "#888888"
BLEU, BORDURE, FOND_ENTETE, FOND_ALTERNE = "#3a5fc0", "#b8c2d8", "#e9edf6", "#f5f7fb"  # PDF
# Couleurs de l'interface
FOND, CARTE, TEXTE, DISCRET, LIGNE = "#f3f5fb", "#ffffff", "#1f2937", "#6b7280", "#e3e8f2"
BLEU_FONCE, BLEU_NUIT, BLEU_CLAIR, BLEU_PALE = "#2f4fa6", "#263f86", "#e8eefc", "#dbe4ff"
VERT_CLAIR, ROUGE_CLAIR, GRIS_CLAIR = "#e3f4e8", "#fde8e8", "#eef0f4"
ORANGE, ROUGE_FONCE = "#c2700a", "#a51f1f"
NULL = "NULL"  # note pas encore connue : ignorée dans la moyenne

MODE_EMPLOI = [
    ("Pour commencer", [
        "Au premier lancement, choisissez votre niveau (L1 à L4), puis entrez votre nom.",
        "Cliquez sur le bouton + pour ajouter une matière.",
    ]),
    ("Saisir ses notes", [
        f"Cliquez dans la case Note d'une matière et tapez votre note, entre 0 et {NOTE_MAX} "
        "(15,5 ou 15.5 sont acceptés).",
        f"Si vous n'avez pas encore la note, laissez {NULL} (ou videz la case) : "
        "la matière ne compte pas dans la moyenne.",
        "La moyenne et les reprises se mettent à jour pendant que vous tapez.",
        "Appuyez sur Entrée pour enregistrer la note : le curseur passe à la matière suivante.",
        "Une note modifiée mais pas encore enregistrée est entourée en orange. "
        "Le bouton Enregistrer (en bas à droite) enregistre toutes les notes modifiées d'un coup.",
        "Si vous fermez l'application avec des notes non enregistrées, elle vous le demande.",
    ]),
    ("Notes de passage et reprises", [
        "L1 : 70    L2 : 70    L3 : 75    L4 : 80",
        "Une matière notée en dessous de la note de passage de votre niveau est une reprise (en rouge).",
        "Chaque matière a un coefficient de 100.",
    ]),
    ("Matières", [
        "Le bouton + (sous la liste) ajoute une matière ; sa note commence à NULL.",
        "✕ à droite d'une matière : la supprime avec sa note.",
    ]),
    ("Exporter et importer", [
        "Exporter… : enregistre votre bulletin en PDF (à imprimer) ou en CSV (LibreOffice / Excel).",
        "Importer… : reprend un bulletin CSV, par exemple pour retrouver vos notes sur un autre ordinateur. "
        "Les matières absentes sont ajoutées, celles déjà présentes prennent la note du fichier.",
        "Un fichier CSV fait à la main fonctionne aussi : une ligne par matière, sous la forme Matière;Note.",
    ]),
    ("Profil", [
        "Profil… : changer de nom ou de niveau.",
        "Tout effacer : supprime votre profil et toutes vos matières pour recommencer à zéro.",
    ]),
]
LIGNES_IGNOREES = {"matière", "matiere", "moyenne", "reprises"}  # en-tête et totaux d'un bulletin exporté

# Taille de police de référence pour une fenêtre de LARGEUR_REF x HAUTEUR_REF
TAILLE_REF, LARGEUR_REF, HAUTEUR_REF = 11, 900, 550


# ---------- Base de données ----------

def dossier_donnees():
    """Dossier de données de l'utilisateur, selon le système (l'exécutable n'est pas modifiable)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    dossier = base / NOM_APP
    ancien = base / ANCIEN_NOM_APP
    if not dossier.exists() and ancien.exists():
        ancien.rename(dossier)  # on garde les notes saisies avant le changement de nom
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


class Base:
    """Profil et notes stockés dans une base SQLite ; chaque modification est enregistrée immédiatement."""

    def __init__(self, chemin=None):
        self.chemin = Path(chemin) if chemin else dossier_donnees() / "moyenne.db"
        self.cnx = sqlite3.connect(self.chemin)
        self.cnx.executescript("""
            CREATE TABLE IF NOT EXISTS profil (
                id     INTEGER PRIMARY KEY CHECK (id = 1),
                niveau TEXT NOT NULL,
                nom    TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS matieres (
                id   INTEGER PRIMARY KEY,
                nom  TEXT NOT NULL UNIQUE COLLATE NOCASE,
                coef REAL NOT NULL,
                note REAL);  -- NULL : note pas encore connue
        """)

    def profil(self):
        """(niveau, nom), ou None au premier lancement."""
        return self.cnx.execute("SELECT niveau, nom FROM profil WHERE id = 1").fetchone()

    def enregistrer_profil(self, niveau, nom):
        with self.cnx:
            self.cnx.execute("INSERT INTO profil (id, niveau, nom) VALUES (1, ?, ?)"
                             " ON CONFLICT (id) DO UPDATE SET niveau = excluded.niveau, nom = excluded.nom",
                             (niveau, nom))

    def matieres(self):
        return [{"nom": nom, "coef": coef, "note": note}
                for nom, coef, note in self.cnx.execute("SELECT nom, coef, note FROM matieres ORDER BY id")]

    def ajouter_matiere(self, nom, coef):
        with self.cnx:
            self.cnx.execute("INSERT INTO matieres (nom, coef) VALUES (?, ?)", (nom, coef))

    def supprimer_matiere(self, nom):
        with self.cnx:
            self.cnx.execute("DELETE FROM matieres WHERE nom = ?", (nom,))

    def changer_note(self, matiere, note):
        with self.cnx:
            self.cnx.execute("UPDATE matieres SET note = ? WHERE nom = ?", (note, matiere))

    def tout_effacer(self):
        with self.cnx:
            self.cnx.execute("DELETE FROM matieres")
            self.cnx.execute("DELETE FROM profil")


# ---------- Calculs ----------

def moyenne(matieres):
    """Moyenne pondérée par les coefficients ; les notes NULL sont ignorées."""
    notees = [m for m in matieres if m["note"] is not None]
    poids = sum(m["coef"] for m in notees)
    return sum(m["note"] * m["coef"] for m in notees) / poids if poids else None


def statut(note, passage):
    if note is None:
        return "En attente"
    return "Validé" if note >= passage else "Reprise"


def nb_reprises(matieres, passage):
    """Nombre de matières notées sous la note de passage (les NULL ne comptent pas)."""
    return sum(1 for m in matieres if m["note"] is not None and m["note"] < passage)


def texte_reprises(n):
    return "Aucune reprise" if n == 0 else f"{n} reprise{'s' if n > 1 else ''}"


def lire_note(texte):
    """Convertit la saisie en note ; vide, NULL ou - signifient « pas encore de note »."""
    texte = texte.strip().replace(",", ".")
    if texte.upper() in ("", NULL, "-"):
        return None
    note = float(texte)  # ValueError si la saisie n'est pas un nombre
    if not 0 <= note <= NOTE_MAX:
        raise ValueError(f"la note doit être comprise entre 0 et {NOTE_MAX}")
    return note


def saisie_autorisee(texte):
    """Filtre la frappe dans une case Note : chiffres jusqu'à NOTE_MAX, ou NULL en cours d'écriture."""
    t = texte.strip()
    if NULL.startswith(t.upper()) or t == "-":
        return True
    if not re.fullmatch(r"\d{0,3}([.,]\d{0,2})?", t):
        return False
    return t in (".", ",") or float(t.replace(",", ".")) <= NOTE_MAX


def fmt(valeur, decimales=None, vide=""):
    """Nombre au format français (virgule décimale)."""
    if valeur is None:
        return vide
    texte = f"{valeur:.{decimales}f}" if decimales is not None else f"{valeur:g}"
    return texte.replace(".", ",")


# ---------- Export ----------

def tableau_export(matieres, passage):
    """Lignes du bulletin : en-tête, une ligne par matière, puis moyenne et reprises."""
    lignes = [["Matière", "Coef", "Note", "Statut"]]
    for m in matieres:
        lignes.append([m["nom"], fmt(m["coef"]), fmt(m["note"], vide=NULL), statut(m["note"], passage)])
    lignes.append(["Moyenne", "", fmt(moyenne(matieres), 2, "—"), ""])
    lignes.append(["Reprises", "", "", texte_reprises(nb_reprises(matieres, passage))])
    return lignes


def couleur_texte(texte):
    if texte in ("Validé", "Aucune reprise"):
        return VERT
    if texte == "Reprise" or texte.endswith(("reprise", "reprises")):
        return ROUGE
    return GRIS if texte in ("En attente", NULL) else None


def exporter_csv(lignes, chemin):
    # ";" et BOM UTF-8 : s'ouvre correctement dans LibreOffice et Excel en français
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(lignes)


def exporter_pdf(matieres, nom, niveau, passage, chemin):
    """Bulletin PDF mis en page sous forme de tableaux (fpdf2, inclus dans l'exécutable)."""
    from fpdf import FPDF

    def latin1(texte):  # les polices intégrées de fpdf ne couvrent que le latin-1
        return str(texte).replace("—", "-").encode("latin-1", "replace").decode("latin-1")

    def rgb(couleur):
        return tuple(int(couleur[i:i + 2], 16) for i in (1, 3, 5))

    def ajuster(texte, largeur):  # coupe un texte trop long pour sa case
        texte = latin1(texte)
        while texte and pdf.get_string_width(texte) > largeur - 4:
            texte = texte[:-4] + "..."
        return texte

    def case(largeur, texte, gras=False, couleur="#000000", fond=None, align="C", h=8):
        pdf.set_font("Helvetica", "B" if gras else "", 10)
        pdf.set_text_color(*rgb(couleur))
        if fond:
            pdf.set_fill_color(*rgb(fond))
        pdf.cell(largeur, h, ajuster(texte, largeur), border=1, align=align, fill=bool(fond))

    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    pdf.set_draw_color(*rgb(BORDURE))
    L = pdf.w - pdf.l_margin - pdf.r_margin

    # Bandeau de titre
    pdf.set_fill_color(*rgb(BLEU))
    pdf.rect(pdf.l_margin, pdf.t_margin, L, 22, style="F")
    pdf.set_xy(pdf.l_margin + 6, pdf.t_margin + 3)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(L - 12, 9, "Bulletin de notes", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + 6)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(L - 12, 6, NOM_APP, new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(pdf.t_margin + 30)

    # Informations de l'étudiant
    etiquette, valeur = L * 0.2, L * 0.3
    for gauche, droite in ((("Nom", nom), ("Niveau", niveau)),
                           (("Note de passage", passage), ("Date", f"{date.today():%d/%m/%Y}"))):
        for lib, val in (gauche, droite):
            case(etiquette, lib, gras=True, fond=FOND_ENTETE, align="L")
            case(valeur, val, align="L")
        pdf.ln()
    pdf.ln(8)

    # Tableau des notes
    colonnes = [("N°", 0.08), ("Matière", 0.42), ("Coefficient", 0.15), ("Note", 0.15), ("Statut", 0.20)]
    for titre, part in colonnes:
        case(L * part, titre, gras=True, couleur="#ffffff", fond=BLEU)
    pdf.ln()
    for i, m in enumerate(matieres, start=1):
        fond = FOND_ALTERNE if i % 2 == 0 else "#ffffff"
        etat = statut(m["note"], passage)
        valeurs = [(i, "#000000"), (m["nom"], "#000000"), (fmt(m["coef"]), "#000000"),
                   (fmt(m["note"], vide=NULL), GRIS if m["note"] is None else "#000000"),
                   (etat, couleur_texte(etat))]
        for (texte, couleur), (titre, part) in zip(valeurs, colonnes):
            case(L * part, texte, gras=titre == "Statut" and m["note"] is not None,
                 couleur=couleur, fond=fond, align="L" if titre == "Matière" else "C")
        pdf.ln()
    pdf.ln(8)

    # Résultats
    moy = moyenne(matieres)
    reprises = nb_reprises(matieres, passage)
    attente = sum(1 for m in matieres if m["note"] is None)
    resultats = [
        ("Moyenne générale", "—" if moy is None else fmt(moy, 2),
         GRIS if moy is None else (VERT if moy >= passage else ROUGE)),
        ("Reprises", texte_reprises(reprises), VERT if reprises == 0 else ROUGE),
        ("Matières en attente de note", str(attente), "#000000"),
    ]
    pdf.set_x(pdf.l_margin + L * 0.4)
    case(L * 0.6, "Résultats", gras=True, couleur="#ffffff", fond=BLEU)
    pdf.ln()
    for lib, val, couleur in resultats:
        pdf.set_x(pdf.l_margin + L * 0.4)
        case(L * 0.35, lib, gras=True, fond=FOND_ENTETE, align="L")
        case(L * 0.25, val, gras=True, couleur=couleur)
        pdf.ln()

    # Légende
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*rgb(GRIS))
    pdf.multi_cell(L, 4.5, latin1(
        f"Note de passage en {niveau} : {passage}. Une matière notée en dessous est une reprise.\n"
        f"{NULL} : note pas encore connue, non comptée dans la moyenne. Coefficient de chaque matière : {COEF_DEFAUT}."))
    pdf.output(str(chemin))


# ---------- Import ----------

def lire_csv(chemin):
    """Lit un bulletin CSV (celui de l'export, ou deux colonnes Matière;Note).

    Renvoie la liste des (matière, note) ; note vaut None pour NULL ou une case vide.
    """
    with open(chemin, newline="", encoding="utf-8-sig") as f:
        contenu = f.read()
    # ";" en priorité : une virgule peut aussi être la décimale d'une note (15,5)
    premiere = contenu.splitlines()[0] if contenu.strip() else ""
    separateur = ";" if ";" in premiere else ("\t" if "\t" in premiere else ",")
    lignes = [l for l in csv.reader(contenu.splitlines(), delimiter=separateur) if l and l[0].strip()]

    col_note = 1
    for l in lignes:  # colonne « Note » d'après l'en-tête, s'il y en a un
        entete = [c.strip().lower() for c in l]
        if entete[0] in ("matière", "matiere") and "note" in entete:
            col_note = entete.index("note")
            break

    resultat = []
    for l in lignes:
        nom = l[0].strip()
        if nom.lower() in LIGNES_IGNOREES:
            continue
        texte = l[col_note] if col_note < len(l) else ""
        try:
            note = lire_note(texte)
        except ValueError:
            raise ValueError(f"Note illisible pour « {nom} » : {texte!r}") from None
        resultat.append((nom, note))
    if not resultat:
        raise ValueError("Aucune matière trouvée dans ce fichier.")
    return resultat


def chemin_ressource(nom):
    """Chemin d'un fichier fourni avec l'application (dans l'exécutable ou à côté du script)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / nom


# ---------- Widgets ----------

class Bouton(tk.Label):
    """Bouton plat coloré (un Label cliquable : les couleurs de tk.Button sont ignorées sur macOS)."""
    STYLES = {  # fond, texte, fond au survol, texte au survol
        "primaire": (BLEU, "#ffffff", BLEU_FONCE, "#ffffff"),
        "secondaire": (CARTE, TEXTE, BLEU_CLAIR, BLEU),
        "barre": (BLEU_FONCE, "#ffffff", BLEU_NUIT, "#ffffff"),
        "lien": (None, BLEU, None, BLEU_FONCE),
        "discret": (CARTE, DISCRET, ROUGE_CLAIR, ROUGE),
        "danger": (CARTE, ROUGE, ROUGE_CLAIR, ROUGE),
        "alerte": (ROUGE, "#ffffff", ROUGE_FONCE, "#ffffff"),
    }

    def __init__(self, parent, texte, commande, style="primaire", font=None, padx=14, pady=6):
        fond, couleur, fond2, couleur2 = self.STYLES[style]
        fond = fond or parent.cget("bg")
        fond2 = fond2 or fond
        super().__init__(parent, text=texte, bg=fond, fg=couleur, font=font, padx=padx, pady=pady,
                         cursor="hand2", highlightthickness=1 if style in ("secondaire", "danger") else 0,
                         highlightbackground=LIGNE)
        self.bind("<Enter>", lambda e: self.config(bg=fond2, fg=couleur2))
        self.bind("<Leave>", lambda e: self.config(bg=fond, fg=couleur))
        self.bind("<ButtonRelease-1>", lambda e: commande())


class BoutonRond(tk.Canvas):
    """Bouton + rond, dont la taille suit la police (pour la mise à l'échelle)."""

    def __init__(self, parent, commande, police, echelle=1.9):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0, cursor="hand2")
        self.police, self.echelle, self.couleur = police, echelle, BLEU
        self.bind("<Enter>", lambda e: self.colorer(BLEU_FONCE))
        self.bind("<Leave>", lambda e: self.colorer(BLEU))
        self.bind("<ButtonRelease-1>", lambda e: commande())
        self.redessiner()

    def colorer(self, couleur):
        self.couleur = couleur
        self.redessiner()

    def redessiner(self):
        d = int(self.police.metrics("linespace") * self.echelle)
        self.config(width=d + 2, height=d + 2)
        self.delete("all")
        self.create_oval(1, 1, d, d, fill=self.couleur, outline="")
        c, l, w = d / 2 + 1, d * 0.22, max(2, round(d * 0.08))
        self.create_line(c - l, c, c + l, c, fill="#ffffff", width=w, capstyle="round")
        self.create_line(c, c - l, c, c + l, fill="#ffffff", width=w, capstyle="round")


class ZoneDefilante(tk.Frame):
    """Cadre avec barre de défilement verticale, affichée seulement si le contenu dépasse."""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.barre = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interieur = tk.Frame(self.canvas, bg=bg)
        self._fenetre = self.canvas.create_window(0, 0, window=self.interieur, anchor="nw")
        self.canvas.configure(yscrollcommand=self.barre.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.interieur.bind("<Configure>", self.ajuster)
        self.canvas.bind("<Configure>", self.ajuster)

    def deborde(self):
        return self.interieur.winfo_reqheight() > self.canvas.winfo_height()

    def ajuster(self, _=None):
        self.canvas.itemconfigure(self._fenetre, width=self.canvas.winfo_width())
        self.canvas.configure(scrollregion=(0, 0, 0, self.interieur.winfo_reqheight()))
        if self.deborde() and not self.barre.winfo_ismapped():
            self.barre.pack(side="right", fill="y", before=self.canvas)
        elif not self.deborde() and self.barre.winfo_ismapped():
            self.barre.pack_forget()
            self.canvas.yview_moveto(0)

    def defiler(self, event):
        if not self.deborde():
            return
        if event.num in (4, 5):  # Linux
            sens = -1 if event.num == 4 else 1
        else:  # Windows et macOS
            sens = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(sens * 2, "units")


# ---------- Interface ----------

class App(tk.Tk):
    def __init__(self, base=None):
        super().__init__()
        self.title(NOM_APP)
        self.configure(bg=FOND)
        try:
            self.icone = tk.PhotoImage(file=chemin_ressource("assets/icone.png"))
            self.iconphoto(True, self.icone)
        except tk.TclError:
            self.icone = None  # icône absente : on garde celle par défaut
        self.geometry(f"{LARGEUR_REF}x{HAUTEUR_REF}")
        self.minsize(680, 460)
        self.base = base or Base()

        # Polices partagées : les modifier redimensionne tous les widgets d'un coup
        self.polices = [tkfont.nametofont(n) for n in ("TkDefaultFont", "TkTextFont", "TkHeadingFont")]
        self.gras = tkfont.Font(weight="bold")
        self.petite = tkfont.Font()
        self.petite_gras = tkfont.Font(weight="bold")
        self.titre = tkfont.Font(weight="bold")
        self.titre_barre = tkfont.Font(weight="bold")
        self.grand = tkfont.Font(weight="bold")
        self.ronds = []
        self._taille = None
        self.styliser()
        self.bind("<Configure>", self.redimensionner)
        self.bind_all("<MouseWheel>", self.molette)
        self.bind_all("<Button-4>", self.molette)
        self.bind_all("<Button-5>", self.molette)
        self.protocol("WM_DELETE_WINDOW", self.quitter)
        self.en_attente = {}  # notes modifiées pas encore enregistrées : {matière: note}
        self.appliquer_taille(TAILLE_REF)

        self.ecran = self.zone = None
        profil = self.base.profil()
        if profil:
            self.ouvrir(*profil)
        else:
            self.ecran_niveau()

    def styliser(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=CARTE, background=CARTE, foreground=TEXTE,
                        arrowcolor=BLEU, bordercolor=LIGNE, lightcolor=CARTE, darkcolor=CARTE, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", CARTE)], selectbackground=[("readonly", CARTE)],
                  selectforeground=[("readonly", TEXTE)], bordercolor=[("focus", BLEU)])
        style.configure("Vertical.TScrollbar", background=LIGNE, troughcolor=CARTE, bordercolor=CARTE,
                        arrowcolor=DISCRET, lightcolor=LIGNE, darkcolor=LIGNE, gripcount=0)
        self.option_add("*TCombobox*Listbox.background", CARTE)
        self.option_add("*TCombobox*Listbox.selectBackground", BLEU)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # --- Mise à l'échelle ---

    def redimensionner(self, event):
        if event.widget is not self:
            return
        echelle = min(event.width / LARGEUR_REF, event.height / HAUTEUR_REF)
        self.appliquer_taille(max(9, min(26, round(TAILLE_REF * echelle))))

    def appliquer_taille(self, taille):
        if taille == self._taille:
            return
        self._taille = taille
        for p in self.polices + [self.gras]:
            p.configure(size=taille)
        self.petite.configure(size=max(8, taille - 2))
        self.petite_gras.configure(size=max(8, taille - 2))
        self.titre.configure(size=round(taille * 1.7))
        self.titre_barre.configure(size=round(taille * 1.3))
        self.grand.configure(size=round(taille * 2))
        self.ronds = [r for r in self.ronds if r.winfo_exists()]
        for r in self.ronds:
            r.redessiner()

    def molette(self, event):
        if self.zone and self.zone.winfo_exists():
            sous = self.winfo_containing(event.x_root, event.y_root)
            if sous is not None and str(sous).startswith(str(self.zone)):
                self.zone.defiler(event)

    # --- Petits outils ---

    def nouvel_ecran(self):
        if self.ecran:
            self.ecran.destroy()
        self.zone = None
        self.ecran = tk.Frame(self, bg=FOND)
        self.ecran.pack(fill="both", expand=True)
        return self.ecran

    def carte(self, parent, **pack):
        cadre = tk.Frame(parent, bg=CARTE, highlightthickness=1, highlightbackground=LIGNE, highlightcolor=LIGNE)
        if pack:
            cadre.pack(**pack)
        return cadre

    def texte(self, parent, texte, font=None, fg=TEXTE, **options):
        return tk.Label(parent, text=texte, font=font, fg=fg, bg=parent.cget("bg"), **options)

    def champ(self, parent, width=24, justify="left", **options):
        return tk.Entry(parent, width=width, justify=justify, relief="flat", bd=0, bg=CARTE, fg=TEXTE,
                        insertbackground=TEXTE, highlightthickness=1, highlightbackground=LIGNE,
                        highlightcolor=BLEU, selectbackground=BLEU_CLAIR, selectforeground=TEXTE, **options)

    def rond(self, parent, commande, echelle=1.9):
        bouton = BoutonRond(parent, commande, self.polices[0], echelle)
        self.ronds.append(bouton)
        return bouton

    def dialogue(self, titre, parent=None):
        fen = tk.Toplevel(self, bg=CARTE)
        fen.title(titre)
        fen.transient(parent or self)
        fen.resizable(False, False)
        cadre = tk.Frame(fen, bg=CARTE, padx=24, pady=20)
        cadre.pack(fill="both", expand=True)
        fen.bind("<Escape>", lambda e: fen.destroy())
        return fen, cadre

    def afficher_dialogue(self, fen):
        fen.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - fen.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - fen.winfo_reqheight()) // 3
        fen.geometry(f"+{max(0, x)}+{max(0, y)}")
        fen.grab_set()

    def message(self, titre, texte, boutons, genre="question", parent=None):
        """Boîte de dialogue assortie à l'application ; renvoie la valeur du bouton cliqué (None si fermée)."""
        fen, cadre = self.dialogue(titre, parent)
        couleur, symbole = {"question": (BLEU, "?"), "attention": (ORANGE, "!"), "danger": (ROUGE, "!"),
                            "erreur": (ROUGE, "✕"), "info": (BLEU, "i"), "succes": (VERT, "✓")}[genre]
        haut = tk.Frame(cadre, bg=CARTE)
        haut.pack(fill="x")
        d = int(self.polices[0].metrics("linespace") * 2.4)
        pastille = tk.Canvas(haut, width=d, height=d, bg=CARTE, highlightthickness=0)
        pastille.create_oval(1, 1, d - 1, d - 1, fill=couleur, outline="")
        pastille.create_text(d / 2, d / 2, text=symbole, fill="#ffffff", font=self.titre_barre)
        pastille.pack(side="left", anchor="n", padx=(0, 16))
        textes = tk.Frame(haut, bg=CARTE)
        textes.pack(side="left", fill="x")
        self.texte(textes, titre, font=self.titre_barre).pack(anchor="w")
        self.texte(textes, texte, fg=DISCRET, justify="left", wraplength=self._taille * 34).pack(anchor="w", pady=(4, 0))

        resultat = []

        def choisir(valeur):
            resultat.append(valeur)
            fen.destroy()

        bas = tk.Frame(cadre, bg=CARTE)
        bas.pack(fill="x", pady=(22, 0))
        for libelle, valeur, style in reversed(boutons):
            Bouton(bas, libelle, lambda v=valeur: choisir(v), style).pack(side="right", padx=(8, 0))
        fen.bind("<Return>", lambda e: choisir(boutons[-1][1]))
        self.afficher_dialogue(fen)
        self.wait_window(fen)
        if parent is not None and parent.winfo_exists():
            parent.grab_set()
        return resultat[0] if resultat else None

    def confirmer(self, titre, texte, oui="Oui", danger=False, parent=None):
        return self.message(titre, texte, [("Annuler", False, "secondaire"),
                                           (oui, True, "alerte" if danger else "primaire")],
                            "danger" if danger else "question", parent) is True

    def informer(self, titre, texte, genre="info", parent=None):
        self.message(titre, texte, [("OK", True, "primaire")], genre, parent)

    def demander_texte(self, titre, question, valider="Valider"):
        fen, cadre = self.dialogue(titre)
        self.texte(cadre, question, font=self.gras).pack(anchor="w")
        saisie = self.champ(cadre, width=30)
        saisie.pack(fill="x", pady=(8, 16), ipady=5)
        saisie.focus_set()
        resultat = []

        def ok():
            resultat.append(saisie.get().strip())
            fen.destroy()

        saisie.bind("<Return>", lambda e: ok())
        boutons = tk.Frame(cadre, bg=CARTE)
        boutons.pack(fill="x")
        Bouton(boutons, valider, ok).pack(side="right")
        Bouton(boutons, "Annuler", fen.destroy, "secondaire").pack(side="right", padx=8)
        self.afficher_dialogue(fen)
        self.wait_window(fen)
        return resultat[0] if resultat else ""

    # --- Premier lancement : niveau puis nom ---

    def carte_accueil(self, etape):
        carte = self.carte(self.nouvel_ecran())
        carte.place(relx=0.5, rely=0.47, anchor="center")
        cadre = tk.Frame(carte, bg=CARTE, padx=48, pady=32)
        cadre.pack()
        if self.icone:
            self.icone_accueil = self.icone.subsample(8)
            tk.Label(cadre, image=self.icone_accueil, bg=CARTE).pack()
        self.texte(cadre, f"Bienvenue sur {NOM_APP}", font=self.titre).pack(pady=(10, 2))
        self.texte(cadre, "Calculez votre moyenne et suivez vos reprises.", fg=DISCRET).pack()
        self.texte(cadre, f"Étape {etape} sur 2", font=self.petite_gras, fg=BLEU).pack(pady=(22, 4))
        return cadre

    def ecran_niveau(self, nom=""):
        cadre = self.carte_accueil(1)
        self.texte(cadre, "Quel est votre niveau ?", font=self.gras).pack()
        niveau = ttk.Combobox(cadre, state="readonly", values=list(NIVEAUX), width=10, justify="center",
                              font=self.polices[0])
        niveau.pack(pady=10)
        info = self.texte(cadre, " ", font=self.petite, fg=DISCRET)
        info.pack()
        niveau.bind("<<ComboboxSelected>>",
                    lambda e: info.config(text=f"Note de passage : {NIVEAUX[niveau.get()]}"))

        def suivant():
            if not niveau.get():
                self.informer("Niveau", "Choisissez votre niveau dans la liste.", "attention")
                return
            self.ecran_nom(niveau.get(), nom)

        Bouton(cadre, "Suivant  →", suivant, padx=22, pady=8).pack(pady=(18, 0))

    def ecran_nom(self, niveau, nom=""):
        cadre = self.carte_accueil(2)
        self.texte(cadre, "Quel est votre nom ?", font=self.gras).pack()
        saisie = self.champ(cadre, width=26, justify="center")
        saisie.insert(0, nom)
        saisie.pack(pady=12, ipady=6)
        saisie.focus_set()
        self.texte(cadre, f"Niveau {niveau}  ·  note de passage {NIVEAUX[niveau]}",
                   font=self.petite, fg=DISCRET).pack()

        def commencer():
            saisi = saisie.get().strip()
            if not saisi:
                self.informer("Nom", "Entrez votre nom.", "attention")
                return
            self.base.enregistrer_profil(niveau, saisi)
            self.ouvrir(niveau, saisi)
            self.after(300, self.fenetre_aide)  # premier lancement : on montre le mode d'emploi

        saisie.bind("<Return>", lambda e: commencer())
        boutons = tk.Frame(cadre, bg=CARTE)
        boutons.pack(pady=(18, 0))
        Bouton(boutons, "←  Retour", lambda: self.ecran_niveau(saisie.get()), "secondaire",
               padx=18, pady=8).pack(side="left", padx=5)
        Bouton(boutons, "Commencer", commencer, padx=22, pady=8).pack(side="left", padx=5)

    # --- Écran principal ---

    def ouvrir(self, niveau, nom):
        self.niveau, self.nom = niveau, nom
        self.passage = NIVEAUX[niveau]
        self.matieres = self.base.matieres()
        ecran = self.nouvel_ecran()

        entete = tk.Frame(ecran, bg=BLEU, padx=20, pady=12)
        entete.pack(fill="x")
        if self.icone:
            self.icone_barre = self.icone.subsample(14)
            tk.Label(entete, image=self.icone_barre, bg=BLEU).pack(side="left", padx=(0, 12))
        titres = tk.Frame(entete, bg=BLEU)
        titres.pack(side="left")
        self.texte(titres, NOM_APP, font=self.titre_barre, fg="#ffffff").pack(anchor="w")
        self.texte(titres, f"{nom}  ·  {niveau}  ·  note de passage {self.passage}",
                   font=self.petite, fg=BLEU_PALE).pack(anchor="w")
        for texte, commande in (("Mode d'emploi", self.fenetre_aide), ("Profil", self.fenetre_profil),
                                ("Exporter", self.fenetre_export), ("Importer", self.importer)):
            Bouton(entete, texte, commande, "barre", padx=12).pack(side="right", padx=3)

        self.corps = tk.Frame(ecran, bg=FOND, padx=24, pady=18)
        self.corps.pack(fill="both", expand=True)
        self.dessiner()

    def dessiner(self, focus=None):
        for w in self.corps.winfo_children():
            w.destroy()
        self.zone = None

        if not self.matieres:  # interface vierge : un grand bouton + au milieu
            vide = tk.Frame(self.corps, bg=FOND)
            vide.place(relx=0.5, rely=0.42, anchor="center")
            self.rond(vide, self.ajouter_matiere, echelle=3.4).pack()
            self.texte(vide, "Ajoutez votre première matière", font=self.gras).pack(pady=(14, 2))
            self.texte(vide, "Cliquez sur le bouton + pour commencer", font=self.petite, fg=DISCRET).pack()
            Bouton(vide, "ou importer un bulletin (CSV)…", self.importer, "lien", font=self.petite).pack(pady=(10, 0))
            return

        # Résumé : trois cartes
        resume = tk.Frame(self.corps, bg=FOND)
        resume.pack(fill="x", pady=(0, 14))
        self.cartes = {}
        for i, cle in enumerate(("moyenne", "reprises", "notees")):
            carte = self.carte(resume)
            carte.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0 if i == 2 else 7))
            resume.columnconfigure(i, weight=1, uniform="cartes")
            interieur = tk.Frame(carte, bg=CARTE, padx=16, pady=10)
            interieur.pack(fill="both")
            titre = {"moyenne": "MOYENNE", "reprises": "REPRISES", "notees": "MATIÈRES NOTÉES"}[cle]
            self.texte(interieur, titre, font=self.petite_gras, fg=DISCRET).pack(anchor="w")
            valeur = self.texte(interieur, "", font=self.grand)
            valeur.pack(anchor="w")
            detail = self.texte(interieur, "", font=self.petite, fg=DISCRET)
            detail.pack(anchor="w")
            self.cartes[cle] = (valeur, detail)

        # Tableau des matières (défile s'il y en a beaucoup)
        carte = self.carte(self.corps, fill="both", expand=True)
        self.zone = ZoneDefilante(carte, CARTE)
        self.zone.pack(fill="both", expand=True, padx=1, pady=1)
        t = self.zone.interieur
        t.columnconfigure(0, weight=1)
        pad = dict(padx=14)
        for j, texte in enumerate(("MATIÈRE", "COEF", "NOTE", "STATUT", "")):
            self.texte(t, texte, font=self.petite_gras, fg=DISCRET).grid(
                row=0, column=j, sticky="w" if j == 0 else "", pady=(12, 8), **pad)

        self.lignes = {}
        for i, m in enumerate(self.matieres):
            r = 2 * i + 1
            tk.Frame(t, bg=LIGNE, height=1).grid(row=r, column=0, columnspan=5, sticky="ew")
            self.texte(t, m["nom"], anchor="w").grid(row=r + 1, column=0, sticky="ew", pady=7, **pad)
            self.texte(t, f"{m['coef']:g}", fg=DISCRET).grid(row=r + 1, column=1, **pad)
            var = tk.StringVar(value=NULL if m["note"] is None else f"{m['note']:g}")
            saisie = self.champ(t, width=7, justify="center", textvariable=var, validate="key",
                                validatecommand=(self.register(saisie_autorisee), "%P"))
            saisie.grid(row=r + 1, column=2, ipady=4, **pad)
            saisie.bind("<FocusIn>", lambda e, c=saisie: c.select_range(0, "end"))
            saisie.bind("<FocusOut>", lambda e, v=var: v.set(NULL) if v.get().strip() == "" else None)
            var.trace_add("write", lambda *_, m=m, v=var: self.changer_note(m, v))
            saisie.bind("<Return>", lambda e, m=m, i=i: self.valider_note(m, i))
            saisie.bind("<KP_Enter>", lambda e, m=m, i=i: self.valider_note(m, i))
            pastille = tk.Label(t, font=self.petite_gras, padx=10, pady=2, width=10)
            pastille.grid(row=r + 1, column=3, **pad)
            Bouton(t, "✕", lambda m=m: self.supprimer_matiere(m), "discret", padx=8, pady=2).grid(
                row=r + 1, column=4, padx=(0, 10))
            self.lignes[m["nom"]] = (saisie, pastille)

        fin = 2 * len(self.matieres) + 1
        tk.Frame(t, bg=LIGNE, height=1).grid(row=fin, column=0, columnspan=5, sticky="ew")
        self.rond(t, self.ajouter_matiere).grid(row=fin + 1, column=0, columnspan=5, pady=12)

        pied = tk.Frame(self.corps, bg=FOND)
        pied.pack(fill="x", pady=(10, 0))
        self.texte(pied, f"{NULL} = note pas encore connue, non comptée dans la moyenne",
                   font=self.petite, fg=DISCRET).pack(side="left")
        Bouton(pied, "Enregistrer", self.enregistrer, padx=18).pack(side="right")
        self.lbl_etat = self.texte(pied, "", font=self.petite_gras)
        self.lbl_etat.pack(side="right", padx=12)
        self.maj()

        if focus in self.lignes:  # nouvelle matière : on descend et on place le curseur dans sa note
            self.update_idletasks()
            self.zone.ajuster()
            self.zone.canvas.yview_moveto(1)
            self.lignes[focus][0].focus_set()

    def maj(self):
        """Met à jour couleurs, statuts et cartes de résumé."""
        pastilles = {"Validé": (VERT, VERT_CLAIR), "Reprise": (ROUGE, ROUGE_CLAIR), "En attente": (DISCRET, GRIS_CLAIR)}
        for m in self.matieres:
            saisie, pastille = self.lignes[m["nom"]]
            etat = statut(m["note"], self.passage)
            couleur, fond = pastilles[etat]
            saisie.config(fg=couleur if m["note"] is not None else DISCRET,
                          highlightbackground=ORANGE if m["nom"] in self.en_attente else LIGNE)
            pastille.config(text=etat, fg=couleur, bg=fond)

        moy = moyenne(self.matieres)
        valeur, detail = self.cartes["moyenne"]
        valeur.config(text="—" if moy is None else fmt(moy, 2),
                      fg=DISCRET if moy is None else (VERT if moy >= self.passage else ROUGE))
        detail.config(text=f"Note de passage : {self.passage}")

        n = nb_reprises(self.matieres, self.passage)
        valeur, detail = self.cartes["reprises"]
        valeur.config(text=str(n), fg=VERT if n == 0 else ROUGE)
        detail.config(text="Aucune reprise" if n == 0 else f"Matière{'s' if n > 1 else ''} sous {self.passage}")

        notees = sum(1 for m in self.matieres if m["note"] is not None)
        valeur, detail = self.cartes["notees"]
        valeur.config(text=f"{notees} / {len(self.matieres)}", fg=TEXTE)
        attente = len(self.matieres) - notees
        detail.config(text="Toutes notées" if attente == 0 else f"En attente : {attente}")
        self.maj_etat()

    def maj_etat(self, message=None):
        if not getattr(self, "lbl_etat", None) or not self.lbl_etat.winfo_exists():
            return
        if self.en_attente:
            n = len(self.en_attente)
            self.lbl_etat.config(text=f"● {n} note{'s' if n > 1 else ''} non enregistrée{'s' if n > 1 else ''}"
                                      "  ·  Entrée pour valider", fg=ORANGE)
        else:
            self.lbl_etat.config(text=message or "✓ Tout est enregistré", fg=VERT)

    def changer_note(self, matiere, var):
        try:
            note = lire_note(var.get())
        except ValueError:
            return  # saisie en cours ou invalide : on garde l'ancienne valeur
        if note == matiere["note"]:
            return
        matiere["note"] = note
        self.en_attente[matiere["nom"]] = note
        self.maj()

    def valider_note(self, matiere, index):
        """Entrée dans une case Note : enregistre la note et passe à la matière suivante."""
        self.enregistrer([matiere["nom"]])
        noms = list(self.lignes)
        if index + 1 < len(noms):
            self.lignes[noms[index + 1]][0].focus_set()
        else:
            self.focus_set()

    def enregistrer(self, noms=None, silencieux=False):
        """Écrit dans la base les notes modifiées (toutes, ou seulement celles de `noms`)."""
        for saisie, _ in getattr(self, "lignes", {}).values():  # case laissée vide : on affiche NULL
            if saisie.winfo_exists() and not saisie.get().strip():
                saisie.delete(0, "end")
                saisie.insert(0, NULL)
        noms = [n for n in (noms if noms is not None else list(self.en_attente)) if n in self.en_attente]
        for nom in noms:
            self.base.changer_note(nom, self.en_attente.pop(nom))
        if silencieux or not getattr(self, "lignes", None):
            return
        self.maj()
        if len(noms) == 1:
            self.maj_etat(f"✓ Note de {noms[0]} enregistrée")
        elif noms:
            self.maj_etat(f"✓ {len(noms)} notes enregistrées")
        else:
            self.maj_etat("✓ Tout est déjà enregistré")

    def quitter(self):
        if self.en_attente:
            choix = self.message("Notes non enregistrées",
                                 "Certaines notes ont été modifiées mais pas enregistrées.",
                                 [("Annuler", None, "secondaire"), ("Ne pas enregistrer", False, "secondaire"),
                                  ("Enregistrer", True, "primaire")], "attention")
            if choix is None:
                return
            if choix:
                self.enregistrer(silencieux=True)
        self.destroy()

    def ajouter_matiere(self):
        nom = self.demander_texte("Nouvelle matière", "Nom de la matière", "Ajouter")
        if not nom:
            return
        if any(m["nom"].lower() == nom.lower() for m in self.matieres):
            self.informer("Matière", f"La matière « {nom} » existe déjà.", "attention")
            return
        self.base.ajouter_matiere(nom, COEF_DEFAUT)
        self.matieres.append({"nom": nom, "coef": COEF_DEFAUT, "note": None})
        self.dessiner(focus=nom)

    def supprimer_matiere(self, matiere):
        if self.confirmer("Supprimer la matière ?",
                          f"La matière « {matiere['nom']} » et sa note seront supprimées.",
                          "Supprimer", danger=True):
            self.en_attente.pop(matiere["nom"], None)
            self.base.supprimer_matiere(matiere["nom"])
            self.matieres.remove(matiere)
            self.dessiner()

    # --- Profil ---

    def fenetre_profil(self):
        fen, cadre = self.dialogue("Profil")
        self.texte(cadre, "Votre profil", font=self.titre_barre).grid(row=0, column=0, columnspan=2,
                                                                    sticky="w", pady=(0, 12))
        self.texte(cadre, "Nom", font=self.gras).grid(row=1, column=0, sticky="w", pady=6)
        nom = self.champ(cadre, width=24)
        nom.insert(0, self.nom)
        nom.grid(row=1, column=1, sticky="w", pady=6, padx=(14, 0), ipady=4)
        self.texte(cadre, "Niveau", font=self.gras).grid(row=2, column=0, sticky="w", pady=6)
        niveau = ttk.Combobox(cadre, state="readonly", values=list(NIVEAUX), width=8, font=self.polices[0])
        niveau.set(self.niveau)
        niveau.grid(row=2, column=1, sticky="w", pady=6, padx=(14, 0))

        def valider():
            if not nom.get().strip():
                self.informer("Profil", "Entrez votre nom.", "attention", parent=fen)
                return
            self.enregistrer(silencieux=True)  # on recharge depuis la base juste après
            self.base.enregistrer_profil(niveau.get(), nom.get().strip())
            fen.destroy()
            self.ouvrir(niveau.get(), nom.get().strip())

        def effacer():
            if self.confirmer("Tout effacer ?", "Votre profil et toutes vos matières seront supprimés. "
                              "Cette action est définitive.", "Tout effacer", danger=True, parent=fen):
                self.en_attente.clear()
                self.base.tout_effacer()
                fen.destroy()
                self.ecran_niveau()

        boutons = tk.Frame(cadre, bg=CARTE)
        boutons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(20, 0))
        Bouton(boutons, "Tout effacer", effacer, "danger").pack(side="left")
        Bouton(boutons, "Valider", valider).pack(side="right")
        Bouton(boutons, "Annuler", fen.destroy, "secondaire").pack(side="right", padx=8)
        self.afficher_dialogue(fen)

    # --- Import ---

    def importer(self):
        chemin = filedialog.askopenfilename(
            parent=self, title="Importer un bulletin", initialdir=Path.home(),
            filetypes=[("CSV", "*.csv"), ("Tous les fichiers", "*")])
        if not chemin:
            return
        try:
            lues = lire_csv(chemin)
        except (OSError, UnicodeDecodeError, ValueError) as err:
            self.informer("Import impossible", f"Ce fichier n'a pas pu être lu : {err}", "erreur")
            return

        existantes = {m["nom"].lower(): m for m in self.matieres}
        nouvelles = [nom for nom, _ in lues if nom.lower() not in existantes]
        maj = len(lues) - len(nouvelles)
        resume = f"{len(lues)} matière(s) trouvée(s) :\n•  {len(nouvelles)} nouvelle(s)\n•  {maj} déjà présente(s)"
        if maj:
            resume += " : leur note sera remplacée"
        if not self.confirmer("Importer ce bulletin ?", resume, "Importer"):
            return

        for nom, note in lues:
            m = existantes.get(nom.lower())
            if m is None:
                self.base.ajouter_matiere(nom, COEF_DEFAUT)
                m = {"nom": nom, "coef": COEF_DEFAUT, "note": None}
                self.matieres.append(m)
                existantes[nom.lower()] = m
            m["note"] = note
            self.en_attente.pop(m["nom"], None)
            self.base.changer_note(m["nom"], note)
        self.dessiner()

    # --- Export ---

    def fenetre_export(self):
        if not self.matieres:
            self.informer("Exporter", "Ajoutez d'abord une matière.")
            return
        fen, cadre = self.dialogue("Exporter")
        self.texte(cadre, "Exporter votre bulletin", font=self.titre_barre).pack(anchor="w")
        self.texte(cadre, "Choisissez le format du fichier :", fg=DISCRET).pack(anchor="w", pady=(2, 14))
        for texte, format_ in (("PDF  ·  à imprimer ou envoyer", "pdf"), ("CSV  ·  LibreOffice / Excel", "csv")):
            Bouton(cadre, texte, lambda f=format_: (fen.destroy(), self.exporter(f)), "secondaire",
                   pady=10).pack(fill="x", pady=4)
        Bouton(cadre, "Annuler", fen.destroy, "lien").pack(pady=(12, 0))
        self.afficher_dialogue(fen)

    def exporter(self, format_):
        chemin = filedialog.asksaveasfilename(
            parent=self, title="Exporter le bulletin", initialdir=Path.home(),
            initialfile=f"bulletin_{self.nom}.{format_}", defaultextension=f".{format_}",
            filetypes=[("PDF", "*.pdf")] if format_ == "pdf" else [("CSV", "*.csv")])
        if not chemin:
            return
        try:
            if format_ == "csv":
                exporter_csv(tableau_export(self.matieres, self.passage), chemin)
            else:
                exporter_pdf(self.matieres, self.nom, self.niveau, self.passage, chemin)
        except ImportError:
            self.informer("Export impossible", "L'export PDF nécessite le module fpdf2 (pip install fpdf2).", "erreur")
            return
        except Exception as err:
            self.informer("Export impossible", f"L'export a échoué : {err}", "erreur")
            return
        self.informer("Bulletin exporté", f"Fichier créé :\n{chemin}", "succes")

    # --- Mode d'emploi ---

    def fenetre_aide(self):
        fen = tk.Toplevel(self, bg=CARTE)
        fen.title(f"Mode d'emploi - {NOM_APP}")
        fen.transient(self)
        fen.geometry("640x540")
        texte = tk.Text(fen, wrap="word", padx=26, pady=20, relief="flat", bd=0, cursor="arrow",
                        background=CARTE, foreground=TEXTE, font=self.polices[0], highlightthickness=0)
        defil = ttk.Scrollbar(fen, command=texte.yview)
        texte.configure(yscrollcommand=defil.set)
        pied = tk.Frame(fen, bg=FOND, pady=10)
        pied.pack(side="bottom", fill="x")
        Bouton(pied, "Fermer", fen.destroy, padx=22).pack()
        defil.pack(side="right", fill="y")
        texte.pack(fill="both", expand=True)

        texte.tag_configure("titre", font=self.titre, foreground=BLEU, spacing3=10)
        texte.tag_configure("section", font=self.gras, foreground=BLEU_FONCE, spacing1=14, spacing3=4)
        texte.tag_configure("point", lmargin1=10, lmargin2=26, spacing1=3)
        texte.insert("end", f"Bienvenue sur {NOM_APP}\n", "titre")
        for section, points in MODE_EMPLOI:
            texte.insert("end", section + "\n", "section")
            for point in points:
                texte.insert("end", f"•  {point}\n", "point")
        texte.configure(state="disabled")


if __name__ == "__main__":
    App().mainloop()
