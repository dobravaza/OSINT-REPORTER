"""
UWAGA: Przed uruchomieniem aplikacji należy:
1. Uzyskać klucz API OpenAI: https://platform.openai.com/account/api-keys
2. Uzyskać klucz API SerpApi: https://serpapi.com/
3. Zastąpić placeholdery 'TWÓJ_KLUCZ_API_*' własnymi kluczami
"""

import json
from serpapi.google_search import GoogleSearch
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import time
import logging
from urllib.parse import urlparse
import csv
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from threading import Thread
from tkinter import font as tkfont
import queue
from openai import OpenAI
import threading
import serpapi
import re
import os

# Konfiguracja loggera
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('osint_scraping.log'),
        logging.StreamHandler()
    ]
)

def zapisz_statystyki(statystyki, nazwa_pliku='statystyki_scrapingu.csv'):
    with open(nazwa_pliku, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['domena', 'udane', 'nieudane', 'całkowity_czas'])
        writer.writeheader()
        for domena, stats in statystyki.items():
            writer.writerow({
                'domena': domena,
                'udane': stats['udane'],
                'nieudane': stats['nieudane'],
                'całkowity_czas': f"{stats['czas_calkowity']:.2f}s"
            })

def pobierz_tresc_artykulu(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()
        
        content = soup.find('article') or soup.find('main') or soup.find('div', class_='content')
        
        if content:
            # Zbieramy paragrafy zachowując strukturę tekstu
            paragraphs = []
            for p in content.find_all(['p', 'h1', 'h2', 'h3']):
                text = p.get_text(strip=True)
                if text:  # Pomijamy puste paragrafy
                    # Jeśli to nagłówek, dodaj dodatkowy odstęp
                    if p.name in ['h1', 'h2', 'h3']:
                        paragraphs.append('\n' + text.upper() + '\n')
                    else:
                        paragraphs.append(text)
            
            # Łączymy paragrafy z odpowiednimi odstępami
            text = '\n\n'.join(paragraphs)
            
            # Dodatkowe czyszczenie tekstu
            text = text.replace('..', '.')  # Usuń podwójne kropki
            text = ' '.join(text.split())  # Normalizuj spacje
            text = text.replace(' .', '.')  # Popraw spacje przed kropkami
            
            # Dodaj odstępy po kropkach jeśli ich nie ma
            text = '. '.join(segment.strip() for segment in text.split('.') if segment.strip())
            text += '.'
        else:
            text = ' '.join([p.get_text(strip=True) for p in soup.find_all('p')])
        
        time.sleep(2)
        return {
            'tekst': text,
            'data_publikacji': None,
            'autorzy': []
        }
    except Exception as e:
        logging.error(f"Nie udało się pobrać treści z {url}: {e}")
        return None

def wykonaj_wyszukiwanie(zapytanie, api_key):
    parametry_wyszukiwania = {
        "q": zapytanie,
        "hl": "pl",
        "gl": "pl",
        "api_key": "TWÓJ_KLUCZ_API_SERPAPI",  # Zastąp swoim kluczem API SerpApi
        "num": 3
    }
    
    try:
        logging.info(f"Wykonuję zapytanie: {zapytanie}")
        wyniki = GoogleSearch(parametry_wyszukiwania).get_dict()
        return wyniki.get('organic_results', [])[:3]  # dodatkowo zabezpieczamy limit
    except Exception as e:
        logging.error(f"Błąd podczas wyszukiwania: {e}")
        return []

def zapisz_raport(wyniki, nazwa_pliku, statystyki):
    with open(nazwa_pliku, 'w', encoding='utf-8') as plik:
        plik.write(f"Szczegółowy Raport OSINT - COVID-19 Impact\n")
        plik.write(f"Data wygenerowania: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        plik.write("=" * 100 + "\n\n")
        
        # Dodanie podsumowania na początku raportu
        plik.write("PODSUMOWANIE SCRAPINGU:\n")
        plik.write("-" * 50 + "\n")
        for domena, stats in statystyki.items():
            plik.write(f"Domena: {domena}\n")
            plik.write(f"Udane pobrania: {stats['udane']}\n")
            plik.write(f"Nieudane pobrania: {stats['nieudane']}\n")
            plik.write(f"Całkowity czas: {stats['czas_calkowity']:.2f}s\n")
            plik.write("-" * 30 + "\n")
        plik.write("\nSZCZEGÓŁOWE WYNIKI:\n")
        plik.write("=" * 100 + "\n\n")
        
        for i, wynik in enumerate(wyniki, 1):
            plik.write(f"ARTYKUŁ #{i}\n")
            plik.write("=" * 50 + "\n")
            plik.write(f"Tytuł: {wynik.get('title', 'Brak tytułu')}\n")
            plik.write(f"Link: {wynik.get('link', 'Brak linku')}\n\n")
            
            # Pobieramy pełną treść artykułu
            tresc = pobierz_tresc_artykulu(wynik.get('link', ''))
            if tresc:
                if tresc['data_publikacji']:
                    plik.write(f"Data publikacji: {tresc['data_publikacji']}\n")
                plik.write("\nSTRESZCZENIE Z WYSZUKIWARKI:\n")
                plik.write(f"{wynik.get('snippet', 'Brak opisu')}\n\n")
                plik.write("PEŁNA TREŚĆ ARTYKUŁU:\n")
                plik.write(f"{tresc['tekst']}\n")
            else:
                plik.write("\nSTRESZCZENIE Z WYSZUKIWARKI:\n")
                plik.write(f"{wynik.get('snippet', 'Brak opisu')}\n")
                plik.write("\nNie udało się pobrać pełnej treści artykułu.\n")
            
            plik.write("\n" + "=" * 100 + "\n\n")

class GPTReportGenerator:
    def __init__(self):
        self.api_key = "TWÓJ_KLUCZ_API_OPENAI"  # Zastąp swoim kluczem API OpenAI
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                timeout=30.0  # Zwiększamy timeout
            )
            logging.info("Klient OpenAI zainicjalizowany")
        except Exception as e:
            logging.error(f"Błąd inicjalizacji klienta OpenAI: {str(e)}")
            raise

    def generate_ai_report(self):
        try:
            if not self.openai_client:
                self.log_message("Klient OpenAI nie jest zainicjalizowany. Sprawdź klucz API.", 'ERROR')
                return
            
            self.log_message("Inicjalizacja generowania raportu AI...", 'PROCESS')
            
            system_prompt = getattr(self, 'current_template', self.default_template)
            template_name = getattr(self, 'current_template_name', 'Domyślny szablon')
            self.log_message(f"Używam szablonu: {template_name}", 'INFO')
            
            self.status_var.set("Generowanie raportu AI...")
            
            # Pobierz tekst i ogranicz jego długość
            scraped_content = self.scraping_text.get("1.0", tk.END)
            max_chars = 4000  # Zmniejszamy maksymalną długość tekstu
            if len(scraped_content) > max_chars:
                scraped_content = scraped_content[:max_chars] + "...[treść skrócona]"
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": scraped_content}
                ],
                temperature=0.7,
                max_tokens=4000,
                presence_penalty=0.3,
                frequency_penalty=0.3
            )

            if response.choices and response.choices[0].message.content:
                report = response.choices[0].message.content
                self.display_ai_report(report)
                self.log_message("Raport AI wygenerowany pomyślnie", 'SUCCESS')
            else:
                self.log_message("Nie udało się wygenerować raportu", 'ERROR')

        except Exception as e:
            self.log_message(f"Błąd podczas generowania raportu: {str(e)}", 'ERROR')
            self.display_ai_report("Wystąpił błąd podczas generowania raportu.")

    def test_api(self):
        """Metoda do testowania połączenia z API"""
        try:
            logging.info("Test połączenia z API...")
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Test."}],
                max_tokens=1
            )
            logging.info("Test API udany")
            return True, "Połączenie z API działa poprawnie"
        except Exception as e:
            logging.error(f"Test API nieudany: {str(e)}")
            return False, f"Błąd połączenia: {str(e)}"

class GoogleScraper:
    def __init__(self):
        self.api_key = ":)"
        self.statystyki = {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def scrape_article(self, url):
        """Ulepszona funkcja scrapowania artykułu z metadanymi"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Metadane
            metadata = {
                "url": url,
                "title": self._extract_title(soup),
                "date": self._extract_date(soup),
                "author": self._extract_author(soup),
                "keywords": self._extract_keywords(soup),
                "description": self._extract_description(soup),
                "language": self._detect_language(soup),
                "word_count": 0,
                "scraping_success": True,
                "error": None
            }
            
            # Treść
            content = self._extract_content(soup)
            if not content:
                metadata["scraping_success"] = False
                metadata["error"] = "Nie udało się pobrać treści"
                return metadata, ""
            
            metadata["word_count"] = len(content.split())
            
            return metadata, content
            
        except Exception as e:
            return {
                "url": url,
                "scraping_success": False,
                "error": str(e)
            }, ""

    def _extract_title(self, soup):
        """Ekstrakcja tytułu"""
        title = soup.title.string if soup.title else ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title["content"]
        return title.strip() if title else ""

    def _extract_date(self, soup):
        """Ekstrakcja daty"""
        date = soup.find("meta", property="article:published_time")
        if date:
            return date["content"]
        return None

    def _extract_author(self, soup):
        """Ekstrakcja autora"""
        author = soup.find("meta", property="article:author")
        if author:
            return author["content"]
        return None

    def _extract_keywords(self, soup):
        """Ekstrakcja słów kluczowych"""
        keywords = soup.find("meta", property="keywords")
        if keywords:
            return keywords["content"].split(",")
        return []

    def _extract_description(self, soup):
        """Ekstrakcja opisu"""
        description = soup.find("meta", property="description")
        if description:
            return description["content"]
        return None

    def _detect_language(self, soup):
        """Ekstrakcja języka"""
        lang = soup.find("meta", property="og:locale")
        if lang:
            return lang["content"].split("-")[0]
        return None

    def _extract_content(self, soup):
        """Ekstrakcja treści artykułu"""
        content = ""
        
        # Próbujemy różne selektory dla różnych stron
        main_content = soup.find('article') or \
                      soup.find('main') or \
                      soup.find(class_=['content', 'article-content', 'post-content']) or \
                      soup.find(id=['content', 'main-content', 'article-content'])
        
        if main_content:
            # Pobieramy wszystkie paragrafy i nagłówki
            for element in main_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li', 'table']):
                text = element.get_text(strip=True)
                if text and len(text) > 20:  # Filtrujemy krótkie fragmenty
                    if element.name.startswith('h'):
                        content += f"\n### {text}\n"
                    elif element.name == 'table':
                        # Próba sformatowania tabeli
                        content += "\n| " + " | ".join(text.split()) + " |\n"
                    else:
                        content += f"{text}\n\n"
        
        # Jeśli nie znaleźliśmy głównej treści, próbujemy pobrać wszystkie znaczące fragmenty
        if not content:
            for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li']):
                text = element.get_text(strip=True)
                if text and len(text) > 30:  # Dłuższy próg dla tekstu bez kontekstu
                    content += f"{text}\n\n"
        
        return content.strip()

    def scrape(self, query, num_results=3):
        try:
            logging.info(f"Rozpoczynam wyszukiwanie dla: {query}")
            
            search = GoogleSearch({
                "q": query,
                "hl": "pl",
                "gl": "pl",
                "api_key": self.api_key,
                "num": num_results,
                "engine": "google"
            })
            
            wyniki = search.get_dict()
            organic_results = wyniki.get('organic_results', [])
            
            processed_results = []
            for result in organic_results:
                url = result.get('link')
                if url:
                    # Pobierz pełną treść artykułu
                    metadata, full_content = self.scrape_article(url)
                    
                    processed_results.append({
                        'title': result.get('title', ''),
                        'link': url,
                        'snippet': result.get('snippet', ''),
                        'content': full_content,
                        'metadata': metadata
                    })
            
            return processed_results
            
        except Exception as e:
            logging.error(f"Błąd podczas scrapowania: {str(e)}")
            raise e

    def get_statistics(self):
        """Zwraca zebrane statystyki"""
        return self.statystyki

class OSINTUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OSINT Report Generator")
        self.root.geometry("1200x900")
        
        # Inicjalizacja klienta OpenAI z hardcodowanym kluczem
        try:
            self.openai_client = OpenAI(
                api_key=":)
            )
            self.log_message("Klient OpenAI zainicjalizowany pomyślnie", 'SUCCESS')
        except Exception as e:
            self.log_message(f"Błąd inicjalizacji klienta OpenAI: {str(e)}", 'ERROR')
            self.openai_client = None
            
        # Dodajemy konfigurację
        self.CONFIG = {
            'MAX_RETRIES': 3,
            'RETRY_DELAY': 2,
            'MAX_TOKENS': 2000,  # Zmniejszamy z 4000 na 2000
            'MAX_INPUT_LENGTH': 4000,  # Zmniejszamy z 12000 na 4000
            'QUEUE_CHECK_INTERVAL': 100
        }
        
        # Rozbudowane predefiniowane tematy OSINT
        self.OSINT_TOPICS = {
            "COVID-19 Biznes": {
                "queries": [
                    "Tomasz Biernacki Dino Polska pandemia COVID-19 rozwój",
                    "Dino Polska wyniki finansowe 2020 2021 2022",
                    "Tomasz Biernacki majątek wzrost pandemia",
                    "Dino Polska strategia rozwój COVID-19",
                    "Tomasz Biernacki wywiad pandemia biznes"
                ],
                "sources": ["biznes", "finanse", "gospodarka"]
            },
            "Blockchain Startupy": {
                "queries": [
                    "blockchain startupy Polska rozwój inwestycje",
                    "polski blockchain innowacje technologie",
                    "kryptowaluty startupy finansowanie Polska",
                    "blockchain inwestorzy venture capital Polska",
                    "polska technologia blockchain rozwój projekty"
                ],
                "sources": ["technologia", "biznes", "startupy"]
            },
            "Elon Musk Relacje": {
                "queries": [
                    "Elon Musk SpaceX Tesla współpraca partnerstwa",
                    "Musk inwestycje projekty technologiczne",
                    "Tesla SpaceX partnerzy strategiczni",
                    "Elon Musk relacje biznesowe technologia",
                    "Musk współpraca firmy technologiczne"
                ],
                "sources": ["technologia", "biznes", "innowacje"]
            },
            "E-sport Polska": {
                "queries": [
                    "e-sport Polska rozwój turnieje gaming",
                    "polski e-sport inwestycje sponsoring",
                    "e-sport organizacje turnieje Polska",
                    "gaming zawodowy rozwój Polska",
                    "e-sport polska liga profesjonalna"
                ],
                "sources": ["gaming", "sport", "technologia"]
            },
            "Jack Ma Aktywność": {
                "queries": [
                    "Jack Ma działalność publiczna Chiny",
                    "Alibaba Jack Ma zarządzanie zmiany",
                    "Jack Ma konflikt rząd chiński biznes",
                    "Jack Ma obecność medialna aktywność",
                    "Alibaba Group kierownictwo zmiany"
                ],
                "sources": ["biznes", "polityka", "technologia"]
            },
            "5G Dezinformacja": {
                "queries": [
                    "5G Polska dezinformacja fake news",
                    "technologia 5G mity Polska",
                    "5G zagrożenia prawda fałsz",
                    "dezinformacja 5G źródła Polska",
                    "5G teorie spiskowe analiza"
                ],
                "sources": ["technologia", "media", "bezpieczeństwo"]
            },
            "Fintech Cyberbezpieczeństwo": {
                "queries": [
                    "fintech cyberbezpieczeństwo zagrożenia Polska",
                    "sektor finansowy cyberataki trendy",
                    "fintech bezpieczeństwo technologie",
                    "cyberbezpieczeństwo bankowość cyfrowa",
                    "fintech ryzyko cyberzagrożenia"
                ],
                "sources": ["technologia", "finanse", "bezpieczeństwo"]
            },
            "AI Healthcare": {
                "queries": [
                    "sztuczna inteligencja medycyna Polska rozwój",
                    "AI healthcare startupy innowacje",
                    "medtech sztuczna inteligencja projekty",
                    "AI służba zdrowia technologie",
                    "healthcare innowacje technologiczne Polska"
                ],
                "sources": ["medycyna", "technologia", "innowacje"]
            }
        }
        
        # Style
        self.style = ttk.Style()
        self.style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'))
        self.style.configure('Info.TLabel', font=('Segoe UI', 10))
        self.style.configure('Action.TButton', padding=8)
        
        # Inicjalizacja zmiennych
        self.topic_var = tk.StringVar()
        self.custom_search_var = tk.StringVar()  # do przechowywania wartości
        self.search_mode = tk.StringVar(value="preset")
        self.status_var = tk.StringVar(value="Gotowy do rozpoczęcia")
        self.articles_var = tk.StringVar(value="3")
        self.queue = queue.Queue()
        
        # Dodaj domyślny szablon
        self.default_template = """Jesteś doświadczonym analitykiem OSINT specjalizującym się w szczegółowych analizach. 
Twoim zadaniem jest stworzenie bardzo szczegółowego raportu zawierającego:

1. PODSUMOWANIE WYKONAWCZE (min. 500 słów)
   - Kluczowe ustalenia z analizy
   - Najważniejsze wnioski i implikacje
   - Krytyczne punkty wymagające uwagi

2. SZCZEGÓŁOWA ANALIZA (min. 1000 słów)
   - Dogłębna analiza głównych tematów
   - Szczegółowe omówienie trendów i wzorców
   - Analiza kluczowych podmiotów i ich roli
   - Analiza danych ilościowych i jakościowych

3. KONTEKST I POWIĄZANIA (min. 500 słów)
   - Szeroki kontekst geopolityczny i ekonomiczny
   - Szczegółowe powiązania między informacjami
   - Analiza historyczna i prognozy

4. WNIOSKI I REKOMENDACJE (min. 500 słów)
   - Szczegółowe wnioski z analizy
   - Konkretne rekomendacje działań
   - Analiza potencjalnych ryzyk i szans
   - Plan działania i następne kroki

Używaj konkretnych danych, liczb i przykładów. Twórz szczegółowe podpunkty i rozbudowane wyjaśnienia."""
        
        # Tworzenie menu
        self.create_menu()
        
        # Tworzenie interfejsu
        self.create_main_interface()
        
        # Inicjalizacja loggera
        self.logger = Logger(self.log_text)
        
        # Dodaj w __init__:
        self.search_mode.trace('w', lambda *args: self.toggle_search_mode())

    def create_menu(self):
        """Tworzy menu główne aplikacji"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Menu Plik
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Plik", menu=file_menu)
        file_menu.add_command(label="Zapisz raport", command=self.save_report)
        file_menu.add_command(label="Eksportuj logi", command=self.export_logs)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjście", command=self.root.quit)
        
        # Menu Narzędzia
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Narzędzia", menu=tools_menu)
        tools_menu.add_command(label="Ustawienia", command=self.show_settings)
        tools_menu.add_command(label="Test API", command=self.test_api_connection)
        
        # Menu Pomoc
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Pomoc", menu=help_menu)
        help_menu.add_command(label="Dokumentacja", command=self.show_docs)
        help_menu.add_command(label="O programie", command=self.show_about)
    
    def create_main_interface(self):
        """Tworzy główny interfejs aplikacji"""
        # Notebook (zakładki)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Panel główny
        main_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(main_frame, text="Panel główny")
        
        # Panel wyszukiwania
        search_frame = ttk.LabelFrame(main_frame, text="Opcje wyszukiwania", padding="10")
        search_frame.pack(fill='x', pady=(0, 10))
        
        # Wybór tematu
        ttk.Label(
            search_frame,
            text="Wybierz predefiniowany temat:",
            style='Info.TLabel'
        ).pack(anchor='w', pady=(0, 5))
        
        self.topic_combo = ttk.Combobox(
            search_frame,
            textvariable=self.topic_var,
            values=list(self.OSINT_TOPICS.keys()),
            state='readonly',
            width=50
        )
        self.topic_combo.pack(fill='x', pady=(0, 10))
        
        # Własne wyszukiwanie
        ttk.Label(
            search_frame,
            text="Lub wprowadź własne zapytanie:",
            style='Info.TLabel'
        ).pack(anchor='w', pady=(0, 5))
        
        ttk.Entry(
            search_frame,
            textvariable=self.custom_search_var,
            width=50
        ).pack(fill='x', pady=(0, 10))
        
        # Opcje scrapowania
        options_frame = ttk.LabelFrame(main_frame, text="Opcje scrapowania", padding="10")
        options_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(
            options_frame,
            text="Liczba artykułów:",
            style='Info.TLabel'
        ).pack(side='left', padx=(0, 10))
        
        ttk.Spinbox(
            options_frame,
            from_=1,
            to=10,
            width=5,
            textvariable=self.articles_var
        ).pack(side='left')
        
        # Przyciski akcji
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(
            button_frame,
            text="Rozpocznij scrapowanie",
            command=self.start_scraping,
            style='Action.TButton'
        ).pack(side='left', padx=5)
        
        ttk.Button(
            button_frame,
            text="Generuj raport AI",
            command=self.generate_ai_report,
            style='Action.TButton'
        ).pack(side='left', padx=5)
        
        # Dodaj po przycisku "Generuj raport AI"
        ttk.Button(
            button_frame,
            text="Wybierz szablon raportu",
            command=self.show_template_window
        ).pack(side='left', padx=5)
        
        # Obszar wyników
        results_frame = ttk.Frame(main_frame)
        results_frame.pack(fill='both', expand=True)
        
        # Logi
        self.log_text = scrolledtext.ScrolledText(
            results_frame,
            height=10,
            font=('Consolas', 9)
        )
        self.log_text.pack(fill='x', pady=(0, 10))
        
        # Wyniki scrapowania
        self.scraping_text = scrolledtext.ScrolledText(
            results_frame,
            height=20,
            font=('Segoe UI', 10)
        )
        self.scraping_text.pack(fill='both', expand=True)

        # Dodajemy zakładkę dla raportu AI
        self.ai_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.ai_frame, text="Raport AI")
        
        # Dodajemy pole tekstowe dla raportu AI
        self.ai_text = scrolledtext.ScrolledText(
            self.ai_frame,
            height=30,
            font=('Segoe UI', 10),
            wrap=tk.WORD
        )
        self.ai_text.pack(fill='both', expand=True)

        # Dodaj po utworzeniu search_frame:
        search_mode_frame = ttk.Frame(search_frame)
        search_mode_frame.pack(fill='x', pady=(0, 10))

        ttk.Radiobutton(
            search_mode_frame,
            text="Predefiniowany temat",
            variable=self.search_mode,
            value="preset"
        ).pack(side='left', padx=(0, 10))

        ttk.Radiobutton(
            search_mode_frame,
            text="Własne zapytanie",
            variable=self.search_mode,
            value="custom"
        ).pack(side='left')

    def check_queue(self):
        try:
            msg_type, data = self.queue.get_nowait()
            self.handle_queue_message(msg_type, data)
        except queue.Empty:
            if self.status_var.get() == "Scrapowanie w toku...":
                self.root.after(self.CONFIG['QUEUE_CHECK_INTERVAL'], self.check_queue)
    
    def handle_queue_message(self, msg_type, data):
        """Obsługa wiadomości z kolejki"""
        if msg_type == "results":
            self.log_message(f"Znaleziono {len(data)} wyników", 'SUCCESS')
            self.display_results(data)
            self.status_var.set("Scrapowanie zakończone")
            # Zapisz do cache'u
            self.results_cache[self.custom_search_var.get()] = data
        elif msg_type == "error":
            error_msg = f"Błąd: {data}"
            self.log_message(error_msg, 'ERROR')
            self.status_var.set(error_msg)

    def start_scraping(self):
        try:
            if not self.validate_input():
                self.log_message("Nieprawidłowe dane wejściowe", 'ERROR')
                return
                
            # Czyszczenie poprzednich wyników
            self.log_message("Czyszczenie poprzednich wyników...", 'PROCESS')
            self.scraping_text.delete(1.0, tk.END)
            self.ai_text.delete(1.0, tk.END)
            
            # Wybór zapytania na podstawie trybu
            if self.search_mode.get() == "custom":
                query = self.custom_search_var.get().strip()
                if not query:
                    self.log_message("Wprowadź własne zapytanie", 'WARNING')
                    return
            else:
                selected_topic = self.topic_var.get()
                if not selected_topic:
                    self.log_message("Wybierz predefiniowany temat", 'WARNING')
                    return
                query = self.OSINT_TOPICS[selected_topic]["queries"][0]
            
            self.log_message(f"Rozpoczynam proces OSINT dla zapytania: {query}", 'PROCESS')
            num_articles = int(self.articles_var.get())
            
            self.log_message(f"Liczba artykułów do pobrania: {num_articles}", 'INFO')
            self.status_var.set("Scrapowanie w toku...")
            
            def scrape_thread():
                try:
                    scraper = GoogleScraper()
                    self.log_message("Inicjalizacja scrapera...", 'INFO')
                    self.log_message("Łączenie z API SerpApi...", 'INFO')
                    results = scraper.scrape(query, num_results=num_articles)
                    
                    if results:
                        self.log_message(f"Pobrano {len(results)} artykułów pomyślnie", 'SUCCESS')
                        self.log_message("Rozpoczynam przetwarzanie artykułów...", 'PROCESS')
                        self.queue.put(("results", results))
                    else:
                        self.log_message("Nie znaleziono żadnych wyników", 'WARNING')
                        
                except Exception as e:
                    error_msg = str(e)
                    self.log_message(f"Błąd podczas scrapowania: {error_msg}", 'ERROR')
                    self.queue.put(("error", error_msg))

            def check_queue():
                try:
                    msg_type, data = self.queue.get_nowait()
                    
                    if msg_type == "results":
                        self.log_message(f"Znaleziono {len(data)} wyników", 'SUCCESS')
                        self.log_message("Rozpoczynam formatowanie wyników...", 'PROCESS')
                        self.display_results(data)
                        self.status_var.set("Scrapowanie zakończone")
                        self.log_message("Formatowanie wyników zakończone", 'SUCCESS')
                        
                    elif msg_type == "error":
                        self.status_var.set(f"Błąd: {data}")
                        self.log_message(f"Błąd podczas scrapowania: {data}", 'ERROR')
                        
                except queue.Empty:
                    if self.status_var.get() == "Scrapowanie w toku...":
                        self.root.after(100, check_queue)
            
            # Uruchom scrapowanie w osobnym wątku
            self.log_message("Uruchamiam wątek scrapowania...", 'INFO')
            threading.Thread(target=scrape_thread, daemon=True).start()
            check_queue()
            
        except Exception as e:
            error_msg = str(e)
            self.log_message(f"Błąd podczas inicjalizacji scrapowania: {error_msg}", 'ERROR')
            self.status_var.set("Błąd podczas scrapowania")

    def validate_input(self):
        try:
            num_articles = int(self.articles_var.get())
            if num_articles < 1 or num_articles > 10:
                self.log_message("Liczba artykułów musi być między 1 a 10", 'WARNING')
                return False
                
            # Sprawdzanie odpowiedniego pola w zależności od trybu
            if self.search_mode.get() == "custom":
                if not self.custom_search_var.get().strip():
                    self.log_message("Wprowadź własne zapytanie", 'WARNING')
                    return False
            else:
                if not self.topic_var.get():
                    self.log_message("Wybierz predefiniowany temat", 'WARNING')
                    return False
                
            return True
        except ValueError:
            self.log_message("Nieprawidłowa wartość liczby artykułów", 'ERROR')
            return False

    def display_results(self, results):
        """Wyświetla wyniki scrapowania"""
        try:
            self.log_message("Rozpoczynam wyświetlanie wyników...", 'PROCESS')
            
            # Wyczyść oba pola tekstowe
            self.scraping_text.delete(1.0, tk.END)
            self.ai_text.delete(1.0, tk.END)
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Pobierz aktualny temat lub własne zapytanie
            if self.search_mode.get() == "custom":
                current_query = self.custom_search_var.get().strip()
                header = f"Szczegółowy Raport OSINT - Własne zapytanie: {current_query}\n"
            else:
                current_topic = self.topic_var.get()
                header = f"Szczegółowy Raport OSINT - {current_topic}\n"
            
            header += f"Data wygenerowania: {current_time}\n"
            header += "=" * 100 + "\n\n"
            
            self.scraping_text.insert(tk.END, header)
            
            if not results:
                self.scraping_text.insert(tk.END, "Nie znaleziono wyników\n")
                self.log_message("Brak wyników do wyświetlenia", 'WARNING')
                return
            
            for i, result in enumerate(results, 1):
                self.log_message(f"Przetwarzanie artykułu {i}/{len(results)}", 'INFO')
                
                article_text = f"""ARTYKUŁ #{i}
{'=' * 50}
Tytuł: {result.get('title', 'Brak tytułu')}
Link: {result.get('link', 'Brak linku')}\n
STRESZCZENIE Z WYSZUKIWARKI:
{result.get('snippet', 'Brak streszczenia')}\n
PEŁNA TREŚĆ:
{result.get('content', 'Brak treści')}\n
{'=' * 100}\n\n"""
                
                self.scraping_text.insert(tk.END, article_text)
                self.scraping_text.update()
            
            self.log_message("Wyświetlanie wyników zakończone pomyślnie", 'SUCCESS')
            
        except Exception as e:
            error_msg = f"Błąd podczas wyświetlania wyników: {str(e)}"
            self.log_message(error_msg, 'ERROR')
            self.scraping_text.insert(tk.END, f"\nBŁĄD: {error_msg}\n")

    def log_message(self, message, level='INFO'):
        """Wrapper dla loggera"""
        if hasattr(self, 'logger'):
            self.logger.log(message, level)
        else:
            print(f"[{level}] {message}")
            
    def generate_ai_report(self):
        try:
            if not self.openai_client:
                self.log_message("Klient OpenAI nie jest zainicjalizowany. Sprawdź klucz API.", 'ERROR')
                return
                
            self.log_message("Inicjalizacja generowania raportu AI...", 'PROCESS')
            
            system_prompt = getattr(self, 'current_template', self.default_template)
            template_name = getattr(self, 'current_template_name', 'Domyślny szablon')
            self.log_message(f"Używam szablonu: {template_name}", 'INFO')
            
            self.status_var.set("Generowanie raportu AI...")
            
            # Pobierz tekst i ogranicz jego długość
            scraped_content = self.scraping_text.get("1.0", tk.END)
            max_chars = 4000  # Zmniejszamy maksymalną długość tekstu
            if len(scraped_content) > max_chars:
                scraped_content = scraped_content[:max_chars] + "...[treść skrócona]"
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": scraped_content}
                ],
                temperature=0.7,
                max_tokens=4000,
                presence_penalty=0.3,
                frequency_penalty=0.3
            )
            
            if response and response.choices:
                report = response.choices[0].message.content
                self.ai_text.delete(1.0, tk.END)
                self.ai_text.insert(tk.END, report)
                self.log_message("Raport AI wygenerowany pomyślnie", 'SUCCESS')
            else:
                self.log_message("Nie udało się wygenerować raportu", 'ERROR')
                
        except Exception as e:
            error_msg = str(e)
            self.log_message(f"Błąd podczas generowania raportu: {error_msg}", 'ERROR')
            self.status_var.set(f"Błąd generowania raportu AI: {error_msg}")

    def display_report(self, report_content):
        """Wyświetla wygenerowany raport AI"""
        self.ai_text.delete(1.0, tk.END)
        self.ai_text.insert(tk.END, report_content)
        self.notebook.select(self.ai_frame)

    def update_topic_description(self, event=None):
        """Aktualizuje opis wybranego tematu"""
        selected = self.topic_var.get()
        if selected in self.OSINT_TOPICS:
            self.topic_description.config(
                text=f"Zapytania: {', '.join(self.OSINT_TOPICS[selected]['queries'])}"
            )

    def save_report(self):
        """Zapisuje raport do pliku"""
        # Implementacja zapisu raportu
        pass

    def export_logs(self):
        """Eksportuje logi do pliku"""
        # Implementacja eksportu logów
        pass

    def show_settings(self):
        """Pokazuje okno ustawień"""
        # Implementacja okna ustawień
        pass

    def test_api_connection(self):
        """Testuje połączenie z API"""
        # Implementacja testu API
        pass

    def show_docs(self):
        """Pokazuje dokumentację"""
        # Implementacja wyświetlania dokumentacji
        pass

    def show_about(self):
        """Pokazuje informacje o programie"""
        # Implementacja okna "O programie"
        pass

    def toggle_search_mode(self, event=None):
        """Przełącza tryb wyszukiwania"""
        mode = self.search_mode.get()
        
        # Znajdź widget Entry w interfejsie
        entry_widget = None
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Entry):
                entry_widget = widget
                break
            
        if mode == "preset":
            self.topic_combo.config(state='readonly')
            if entry_widget:
                entry_widget.config(state='disabled')
        else:
            self.topic_combo.config(state='disabled')
            if entry_widget:
                entry_widget.config(state='normal')

    def show_template_window(self):
        template_window = ReportTemplateWindow(self.root)
        template_window.callback = self.apply_template
        
    def apply_template(self, template_content, template_name):
        """Aplikuje wybrany szablon"""
        self.current_template = template_content
        self.current_template_name = template_name
        self.log_message(f"Aktywowano szablon: {template_name}", 'SUCCESS')

    def save_custom_instructions(self):
        custom_text = self.template_editor.get("1.0", tk.END).strip()
        if custom_text:
            self.templates["Własny szablon"]["prompt"] = custom_text
            messagebox.showinfo(
                "Sukces",
                "Własne instrukcje zostały zapisane jako szablon"
            )
            # Aktualizuj podgląd
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, custom_text)
        else:
            messagebox.showwarning(
                "Pusty szablon",
                "Proszę wprowadzić treść własnych instrukcji"
            )

    def use_template(self):
        selected = self.template_var.get()
        if selected == "Własny szablon":
            custom_text = self.template_editor.get("1.0", tk.END).strip()
            if not custom_text or custom_text == "Wprowadź własne instrukcje dla AI...":
                messagebox.showwarning(
                    "Pusty szablon",
                    "Proszę wprowadzić własne instrukcje przed zatwierdzeniem"
                )
                return
            template_content = custom_text
        else:
            template_content = self.templates[selected]["prompt"]
        
        # Przekaż szablon do głównego okna
        self.callback(template_content, selected)
        self.log_message(f"Załadowano szablon: {selected}", 'SUCCESS')
        self.window.destroy()

    def perform_search(self, topic):
        """Wykonuje wyszukiwanie OSINT dla wybranego tematu"""
        if topic in self.OSINT_TOPICS:
            queries = self.OSINT_TOPICS[topic]["queries"]
            sources = self.OSINT_TOPICS[topic]["sources"]
            
            all_results = []
            for query in queries:
                self.log_message(f"Wyszukiwanie: {query}", 'INFO')
                results = self.search_api.search(
                    query, 
                    num_results=self.num_results,
                    source_filter=sources
                )
                all_results.extend(results)
            
            # Deduplikacja i sortowanie wyników
            unique_results = self.deduplicate_results(all_results)
            return self.sort_results_by_relevance(unique_results)
        else:
            return self.search_api.search(topic, num_results=self.num_results)

class Logger:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.colors = {
            'INFO': '#0066cc',      # Niebieski
            'SUCCESS': '#00cc66',   # Zielony
            'WARNING': '#ff9900',   # Pomarańczowy
            'ERROR': '#cc0000',     # Czerwony
            'PROCESS': '#6600cc'    # Fioletowy
        }

    def log(self, message, level='INFO'):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        icon = {
            'INFO': '🔵',
            'SUCCESS': '✅',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'PROCESS': '⚙️'
        }.get(level, '📝')
        
        log_message = f"[{timestamp}] {icon} {message}\n"
        
        # Dodaj tekst z odpowiednim tagiem koloru
        start_index = self.text_widget.index("end-1c")
        self.text_widget.insert(tk.END, log_message)
        end_index = self.text_widget.index("end-1c")
        
        # Zastosuj kolor do całej linii
        self.text_widget.tag_add(level, start_index, end_index)
        
        # Przewiń do najnowszego logu
        self.text_widget.see(tk.END)
        self.text_widget.update()

class ReportTemplateWindow:
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("Szablony Raportów OSINT")
        # Zwiększamy rozmiar okna z 800x600 na 1000x800
        self.window.geometry("1000x800")
        
        # Dodajemy minimalny rozmiar okna, żeby nie można było go za bardzo zmniejszyć
        self.window.minsize(900, 700)
        
        # Opcjonalnie: wyśrodkowanie okna na ekranie
        self.window.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = (self.window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.window.winfo_screenheight() // 2) - (height // 2)
        self.window.geometry(f'+{x}+{y}')
        
        # Ulepszone szablony OSINT
        self.templates = {
            "Własny szablon": {
                "prompt": "Wprowadź własne instrukcje dla AI..."
            },
            "Analiza Biznesowa OSINT": {
                "prompt": """Jesteś ekspertem OSINT (Open Source Intelligence) specjalizującym się w analizie biznesowej. 
Przeanalizuj dostarczone dane i stwórz szczegółowy raport zawierający:

1. PODSUMOWANIE WYKONAWCZE
   - Kluczowe ustalenia i wnioski
   - Najważniejsze trendy i wzorce
   - Krytyczne informacje biznesowe

2. ANALIZA PODMIOTU
   - Struktura organizacyjna i własność
   - Historia i rozwój
   - Kluczowe osoby (zarząd, kierownictwo)
   - Lokalizacje i zasięg działania

3. ANALIZA RYNKOWA
   - Pozycja rynkowa i udział w rynku
   - Główni konkurenci i ich działania
   - Przewagi konkurencyjne
   - Trendy rynkowe wpływające na podmiot

4. ANALIZA FINANSOWA
   - Źródła finansowania
   - Inwestycje i przejęcia
   - Wskaźniki finansowe
   - Potencjalne ryzyka finansowe

5. RELACJE I POWIĄZANIA
   - Kluczowi partnerzy biznesowi
   - Powiązania kapitałowe
   - Relacje z interesariuszami
   - Sieci wpływów

6. REPUTACJA I WIZERUNEK
   - Obecność w mediach
   - Opinie klientów i partnerów
   - Kontrowersje i problemy wizerunkowe
   - Działania CSR i PR

7. ANALIZA RYZYK
   - Ryzyka operacyjne
   - Ryzyka prawne i regulacyjne
   - Ryzyka reputacyjne
   - Potencjalne zagrożenia

8. REKOMENDACJE
   - Kluczowe obszary wymagające uwagi
   - Sugerowane działania
   - Możliwości rozwoju
   - Strategie minimalizacji ryzyk

Użyj konkretnych danych i przykładów z dostarczonych materiałów. Zachowaj obiektywizm i profesjonalizm w analizie."""
            },
            "Analiza Technologiczna OSINT": {
                "prompt": """Jesteś ekspertem OSINT specjalizującym się w analizie technologicznej.
Przeanalizuj dostarczone dane i stwórz szczegółowy raport technologiczny zawierający:

1. PODSUMOWANIE TECHNICZNE
   - Główne odkrycia technologiczne
   - Kluczowe technologie i rozwiązania
   - Krytyczne aspekty techniczne

2. INFRASTRUKTURA TECHNICZNA
   - Architektura systemów
   - Używane technologie i narzędzia
   - Infrastruktura sieciowa
   - Centra danych i hostingi

3. ROZWÓJ TECHNOLOGICZNY
   - Roadmapa technologiczna
   - Innowacje i patenty
   - Projekty R&D
   - Kierunki rozwoju technologicznego

4. BEZPIECZEŃSTWO
   - Polityki bezpieczeństwa
   - Certyfikacje i zgodność
   - Potencjalne luki i zagrożenia
   - Incydenty bezpieczeństwa

5. ZESPÓŁ TECHNICZNY
   - Struktura zespołów
   - Kluczowe kompetencje
   - Rekrutacje i trendy zatrudnienia
   - Współpraca z zewnętrznymi ekspertami

6. ANALIZA KONKURENCYJNA
   - Porównanie technologii konkurencji
   - Przewagi technologiczne
   - Luki technologiczne
   - Trendy rynkowe

7. RYZYKA TECHNOLOGICZNE
   - Długoterminowa stabilność
   - Skalowalność rozwiązań
   - Zależności technologiczne
   - Przestarzałe technologie

8. REKOMENDACJE TECHNICZNE
   - Sugerowane ulepszenia
   - Priorytety rozwojowe
   - Strategia modernizacji
   - Plan minimalizacji ryzyk

Wykorzystaj konkretne informacje z dostarczonych materiałów. Zachowaj techniczny profesjonalizm."""
            },
            "Analiza Zagrożeń OSINT": {
                "prompt": """Jesteś ekspertem OSINT specjalizującym się w analizie zagrożeń i bezpieczeństwa.
Przeanalizuj dostarczone dane i stwórz szczegółowy raport bezpieczeństwa zawierający:

1. PODSUMOWANIE ZAGROŻEŃ
   - Krytyczne zagrożenia
   - Poziomy ryzyka
   - Priorytety bezpieczeństwa

2. ANALIZA ŚRODOWISKA ZAGROŻEŃ
   - Aktualne zagrożenia
   - Trendy w cyberbezpieczeństwie
   - Geopolityczne czynniki ryzyka
   - Zagrożenia sektorowe

3. PODATNOŚCI I SŁABE PUNKTY
   - Zidentyfikowane podatności
   - Potencjalne wektory ataku
   - Luki w zabezpieczeniach
   - Słabości organizacyjne

4. ANALIZA INCYDENTÓW
   - Historia incydentów
   - Wzorce ataków
   - Skuteczność odpowiedzi
   - Wyciągnięte wnioski

5. OCENA ZABEZPIECZEŃ
   - Istniejące kontrole
   - Skuteczność zabezpieczeń
   - Zgodność z regulacjami
   - Luki w ochronie

6. ANALIZA WPŁYWU
   - Potencjalne skutki ataków
   - Wpływ na działalność
   - Straty finansowe
   - Szkody reputacyjne

7. PRZECIWDZIAŁANIE ZAGROŻENIOM
   - Strategie obronne
   - Plany reagowania
   - Procedury bezpieczeństwa
   - Szkolenia i świadomość

8. REKOMENDACJE BEZPIECZEŃSTWA
   - Priorytetowe działania
   - Ulepszenia zabezpieczeń
   - Plan wdrożenia
   - Monitoring i ewaluacja

Wykorzystaj konkretne przykłady z dostarczonych materiałów. Zachowaj profesjonalizm w analizie bezpieczeństwa."""
            }
        }
        
        # Zmienna do przechowywania wybranego szablonu
        self.template_var = tk.StringVar(value="Własny szablon")
        self.template_var.trace('w', lambda *args: self.update_preview())
        
        self.create_widgets()
        
    def create_widgets(self):
        # Panel wyboru szablonu
        template_frame = ttk.LabelFrame(self.window, text="Wybierz szablon raportu", padding=10)
        template_frame.pack(fill='x', padx=10, pady=5)
        
        # Przyciski - przenosimy na górę
        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(
            button_frame,
            text="Zatwierdź własny szablon",
            command=self.save_and_use_template,
            style='Action.TButton'
        ).pack(side='right', padx=5)
        
        ttk.Button(
            button_frame,
            text="Anuluj",
            command=self.window.destroy,
            style='Secondary.TButton'
        ).pack(side='right')
        
        # Dodanie variable do RadioButton
        for template_name in self.templates.keys():
            ttk.Radiobutton(
                template_frame,
                text=template_name,
                value=template_name,
                variable=self.template_var,
                command=self.update_preview
            ).pack(anchor='w', pady=2)
            
        # Panel podglądu
        preview_frame = ttk.LabelFrame(self.window, text="Podgląd szablonu", padding=10)
        preview_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.preview_text = scrolledtext.ScrolledText(
            preview_frame,
            wrap=tk.WORD,
            font=('Segoe UI', 10)
        )
        self.preview_text.pack(fill='both', expand=True)
        
        # Panel edycji własnego szablonu
        self.custom_template_frame = ttk.LabelFrame(self.window, text="Edycja własnego szablonu", padding=10)
        self.custom_template_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.template_editor = scrolledtext.ScrolledText(
            self.custom_template_frame,
            wrap=tk.WORD,
            font=('Segoe UI', 10),
            height=10
        )
        self.template_editor.pack(fill='both', expand=True)

    def update_preview(self):
        selected = self.template_var.get()
        if selected == "Własny szablon":
            # Pokaż pole edycji
            self.custom_template_frame.pack(fill='both', expand=True, padx=10, pady=5)
            self.preview_text.delete(1.0, tk.END)
            if "prompt" in self.templates["Własny szablon"] and self.templates["Własny szablon"]["prompt"] != "Wpisz własne instrukcje dla AI...":
                self.preview_text.insert(tk.END, self.templates["Własny szablon"]["prompt"])
                self.template_editor.delete(1.0, tk.END)
                self.template_editor.insert(tk.END, self.templates["Własny szablon"]["prompt"])
            else:
                self.preview_text.insert(tk.END, "Wprowadź własny szablon poniżej i zatwierdź go...")
        else:
            # Ukryj pole edycji
            self.custom_template_frame.pack_forget()
            if selected in self.templates:
                self.preview_text.delete(1.0, tk.END)
                self.preview_text.insert(tk.END, self.templates[selected]["prompt"])

    def save_and_use_template(self):
        """Metoda łącząca zapisanie i użycie własnego szablonu"""
        selected = self.template_var.get()
        if selected == "Własny szablon":
            custom_text = self.template_editor.get("1.0", tk.END).strip()
            if custom_text:
                self.templates["Własny szablon"]["prompt"] = custom_text
                self.callback(custom_text, "Własny szablon")
                self.window.destroy()
            else:
                messagebox.showwarning(
                    "Pusty szablon",
                    "Proszę wprowadzić treść własnego szablonu"
                )
        else:
            self.callback(self.templates[selected]["prompt"], selected)
            self.window.destroy()

def main():
    root = tk.Tk()
    app = OSINTUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 