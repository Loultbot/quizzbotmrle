import asyncio
import websockets
import json
import html
import os
import random
import re
from datetime import datetime, timedelta
import requests  # Pour faire des requêtes HTTP
import unicodedata

def normalize_string(s):
    return unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode().casefold()

# Fichiers de données centralisés
data_file = "player_data.json"
questions_file = "questions.json"

# Chargement des données des joueurs à partir d'un fichier JSON
def load_data():
    if os.path.exists(data_file):
        with open(data_file, "r") as f:
            data = json.load(f)
            return data.get("coins", {})
    return {}

# Sauvegarde des données des joueurs
def save_data(player_coins):
    data = {"coins": player_coins}
    with open(data_file, "w") as f:
        json.dump(data, f)

# Chargement des questions à partir d'un fichier JSON
def load_questions():
    if os.path.exists(questions_file):
        with open(questions_file, "r") as f:
            return json.load(f)
    return []

# Sauvegarde des questions dans un fichier JSON
def save_questions(questions):
    with open(questions_file, "w") as f:
        json.dump(questions, f)

# Variables globales
player_last_played = {}
connected_users = {}
current_question = None
correct_answer = None
question_asked_time = None
is_bot_active = True
last_hour_message = None
DEFAULT_COINS = 10
received_answers = set()  # Ajout de la variable pour stocker les réponses déjà reçues

async def send_message(websocket, message_data):
    message_json = json.dumps(message_data)
    await websocket.send(message_json)

async def generate_question_from_mistral():
    api_key = "api key here"  # Votre clé API Mistral
    url = "https://api.mistral.ai/v1/chat/completions"  # URL de l'API Mistral

    topics = ["musique", "cinéma et séries", "célébrités et potins", "horreur et paranormal", "pop culture",
               "films cultes", "pop culture musique"]

    selected_topic = random.choice(topics)

    prompt = (f"Génère une question en français avec une seule réponse (courte) possible sur le thème suivant : {selected_topic}. "
              "Fournis uniquement la question suivie de la réponse.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 100,  # Ajuster selon vos besoins
        "temperature": 1.5,
        "top_p": 1,
        "stream": False,
        "response_format": {"type": "text"},
        "tools": [],
        "tool_choice": "auto",
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "n": 1
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        generated_text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"Mistral: {generated_text}")
        return parse_question_response(generated_text)
    else:
        print(f"Échec de la génération de la question : {response.status_code}")
        print(f"Réponse : {response.text}")
        return None

async def check_answer_from_mistral(question, correct_answer, user_answer):
    api_key = "HPVn28TLjprLwdE2PO5EyEdLK48z7nIT"  # Votre clé API Mistral
    url = "https://api.mistral.ai/v1/chat/completions"  # URL de l'API Mistral

    prompt = f"{question} Une réponse possible est {correct_answer}. Est-ce que la réponse suivante est correcte : {user_answer}. Réponse (oui/non uniquement) : "

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 100,  # Ajuster selon vos besoins
        "temperature": 1.5,
        "top_p": 1,
        "stream": False,
        "response_format": {"type": "text"},
        "tools": [],
        "tool_choice": "auto",
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "n": 1
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        generated_text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"Mistral: {generated_text}")
        return generated_text
    else:
        print(f"Échec de la vérification de la réponse : {response.status_code}")
        print(f"Réponse : {response.text}")
        return None

async def generate_clue_from_mistral(question, answer):
    api_key = "HPVn28TLjprLwdE2PO5EyEdLK48z7nIT"  # Votre clé API Mistral
    url = "https://api.mistral.ai/v1/chat/completions"  # URL de l'API Mistral

    prompt = f"Trouve un indice très court pour aider à répondre à la question suivante : {question}. La réponse est : {answer}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 100,  # Ajuster selon vos besoins
        "temperature": 1.5,
        "top_p": 1,
        "stream": False,
        "response_format": {"type": "text"},
        "tools": [],
        "tool_choice": "auto",
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "n": 1
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        global clue
        generated_text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"Mistral: {generated_text}")
        clue = generated_text
        return generated_text
    else:
        print(f"Échec de la génération de l'indice : {response.status_code}")
        print(f"Réponse : {response.text}")
        return None

def parse_question_response(generated_text):
    try:
        # Extraire la question et la réponse
        match = re.match(r"(.*?\?)\s*(réponse\s*:\s*)?(.*)", generated_text, re.DOTALL)
        if match:
            question = match.group(1).strip()
            answer = match.group(3).strip().lower()
            # Supprimer le préfixe "réponse :" s'il est présent
            answer = re.sub(r'^réponse\s*:\s*', '', answer)
            return {"question": question, "answer": answer}
        else:
            print("Format de réponse incorrect.")
            return None

    except Exception as e:
        print(f"Erreur de parsing: {e}")
        return None

def hide_answer(correct_answer):
    answer_length = len(correct_answer)
    random_index = random.randint(0, answer_length - 1)  # 0-based indexing

    hidden_answer = ' '.join(
        '|' if char == ' ' else (char if i == random_index else '_')
        for i, char in enumerate(correct_answer)
    )

    return hidden_answer

async def connect_to_loult_family(player_coins):
    uri = "wss://loult.family/socket/"
    headers = {
        'Cookie': 'id=d48380818117c51fa36aa0d0aedd5207',
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://loult.family/'
    }

    global current_question, correct_answer, question_asked_time, is_bot_active, last_hour_message, received_answers

    questions = []  # load_questions()

    while True:
        try:
            async with websockets.connect(uri, additional_headers=headers) as websocket:
                message = json.dumps({"type": "greeting", "content": "Bonjour, Loult.family!"})
                await websocket.send(message)
                print(f"Envoyé: {message}")

                error_count = 0

                while True:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1)
                        if isinstance(response, str):
                            data = json.loads(response)

                            if data.get("type") == "userlist":
                                for user in data["users"]:
                                    userid = user["userid"]
                                    name = user["params"]["name"]
                                    adjective = user["params"]["adjective"]
                                    connected_users[userid] = (name, adjective)
                                    if userid not in player_coins:
                                        player_coins[userid] = DEFAULT_COINS

                            elif data.get("type") == "msg":
                                msg_content = html.unescape(data.get("msg")).lower().strip()
                                userid = data.get("userid")
                                username = connected_users.get(userid, ("Unknown", ""))[0]

                                if userid not in player_coins:
                                    player_coins[userid] = DEFAULT_COINS
                                    save_data(player_coins)

                                if is_bot_active:
                                    if msg_content == "!quizz":  # and userid == "75bf8cd1e1dbdc7e":
                                        if not questions:
                                            question = await generate_question_from_mistral()
                                            if question:
                                                questions.append(question)
                                                save_questions(questions)

                                        if questions:
                                            current_question_data = questions.pop(0)
                                            current_question = current_question_data["question"]
                                            correct_answer = current_question_data["answer"].lower()
                                            question_asked_time = datetime.now()
                                            received_answers.clear()  # Réinitialiser les réponses reçues
                                            response_message = {"type": "msg", "msg": f"Question: {current_question}"}
                                            await send_message(websocket, response_message)
                                        else:
                                            response_message = {"type": "msg", "msg": "Aucune question disponible."}
                                            await send_message(websocket, response_message)

                                    elif current_question and msg_content.startswith("!mrle"):
                                        msg_content = msg_content.replace("!mrle", "").strip()
                                        print(f"Réponse utilisateur: {msg_content}")

                                        # Vérifiez si la réponse a déjà été reçue
                                        if msg_content in received_answers:
                                            response_message = {
                                                "type": "bot",
                                                "msg": f"{username}, votre réponse a déjà été enregistrée. Attendez la prochaine question."
                                            }
                                            await send_message(websocket, response_message)
                                            continue

                                        received_answers.add(msg_content)  # Ajouter la réponse à l'ensemble des réponses reçues

                                        check_answer = await check_answer_from_mistral(current_question, correct_answer, msg_content)
                                        if "oui" in check_answer.lower() and normalize_string(msg_content) == normalize_string(correct_answer):
                                            error_count = 0
                                            player_coins[userid] += 5
                                            response_message = {
                                                "type": "me",
                                                "msg": f"Bravo {username}! Bonne réponse. +5 coins. Solde: {player_coins[userid]}. La bonne réponse était: {correct_answer}"
                                            }
                                            await send_message(websocket, response_message)
                                            save_data(player_coins)

                                            current_question = None
                                            correct_answer = None
                                            question_asked_time = None
                                            received_answers.clear()  # Réinitialiser les réponses reçues

                                            if not questions:
                                                question = await generate_question_from_mistral()
                                                if question:
                                                    questions.append(question)
                                                    save_questions(questions)

                                            if questions:
                                                current_question_data = questions.pop(0)
                                                current_question = current_question_data["question"]
                                                correct_answer = current_question_data["answer"].lower()
                                                question_asked_time = datetime.now()
                                                received_answers.clear()  # Réinitialiser les réponses reçues
                                                response_message = {"type": "msg", "msg": f"Nouvelle question: {current_question}"}
                                                await send_message(websocket, response_message)

                                        elif "non" in check_answer.lower():
                                            error_count += 1
                                            if error_count >= 4:
                                                error_count = 0
                                                # Generate clue from mistral
                                                # await generate_clue_from_mistral(current_question, correct_answer)
                                                # clue_message = f"Voici un indice pour vous aider: {clue}"
                                                # await send_message(websocket, {"type": "msg", "msg": clue_message})

                                                # Send only one letter of the answer, the rest being replaced by underscores
                                                hidden_answer = hide_answer(correct_answer)
                                                clue_message = f"Voici un indice pour vous aider: {hidden_answer}"
                                                await send_message(websocket, {"type": "msg", "msg": clue_message})
                                            response_message = {
                                                "type": "bot",
                                                "msg": f"Non {username}, la réponse n'est pas correcte. Essayez encore."
                                            }
                                            await send_message(websocket, response_message)

                        current_time = datetime.now()
                        if last_hour_message is None or current_time - last_hour_message >= timedelta(hours=1):
                            last_hour_message = current_time
                            if is_bot_active:
                                await send_message(websocket, {"type": "msg", "msg": "C'est Dino qui t'aime"})

                    except asyncio.TimeoutError:
                        pass
                    except Exception as recv_error:
                        print(f"Erreur lors de la réception du message : {recv_error}")

                    if current_question and question_asked_time is not None:
                        if datetime.now() - question_asked_time >= timedelta(seconds=300):
                            response_message = {"type": "msg", "msg": f"Temps écoulé ! La bonne réponse était: {correct_answer}"}
                            await send_message(websocket, response_message)

                            if not questions:
                                question = await generate_question_from_mistral()
                                if question:
                                    questions.append(question)
                                    save_questions(questions)

                            if questions:
                                current_question_data = questions.pop(0)
                                current_question = current_question_data["question"]
                                correct_answer = current_question_data["answer"].lower()
                                question_asked_time = datetime.now()
                                received_answers.clear()  # Réinitialiser les réponses reçues
                                response_message = {"type": "msg", "msg": f"Nouvelle question: {current_question}"}
                                await send_message(websocket, response_message)

        except Exception as e:
            print(f"Erreur lors de la connexion : {e}")
            print("Reconnexion dans 5 secondes...")
            await asyncio.sleep(5)

async def main():
    player_coins = load_data()
    await connect_to_loult_family(player_coins)

if __name__ == "__main__":
    asyncio.run(main())
