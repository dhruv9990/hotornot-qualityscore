from flask import Flask, render_template, request, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import random
import os
import json
import time

app = Flask(__name__)

# --- In-Memory Cache ---
_cache = {}
_cache_time = 0
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)

# --- Google Sheets Setup ---
def get_google_sheets_client():
    """Establishes connection with Google Sheets."""
    print("--- Attempting to get Google Sheets client ---")
    try:
        creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
        if not creds_json:
            print("!!! ERROR: GOOGLE_SHEETS_CREDENTIALS environment variable not found or is empty.")
            return None
        
        print(f"--- Found credentials of type {type(creds_json)} and length {len(creds_json)} ---")
        creds_dict = json.loads(creds_json)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        print("--- Successfully authorized Google Sheets client ---")
        return client
    except Exception as e:
        print(f"!!! CRITICAL ERROR in get_google_sheets_client: {e}")
        return None

def get_sheets_data():
    """Fetches and processes data from Google Sheets, with caching."""
    global _cache, _cache_time

    # Check if cache is still valid
    if _cache and (time.time() - _cache_time < CACHE_DURATION):
        print("--- Using cached data ---")
        return _cache.get('tweet_lookup', {}), _cache.get('tweet_ids', [])

    print("--- Cache expired or empty, fetching new data ---")
    client = get_google_sheets_client()
    if not client:
        print("!!! ERROR: Could not get Google Sheets client. Aborting data fetch.")
        return {}, []

    try:
        print("--- Opening spreadsheet 'HotOrNotTweets' ---")
        sheet = client.open("HotOrNotTweets").worksheet("Tweets")
        print("--- Getting all records from 'Tweets' worksheet ---")
        data = sheet.get_all_records()
        if not data:
            print("!!! WARNING: No data found in 'Tweets' worksheet.")
            return {}, []
        print(f"--- Found {len(data)} records in sheet. ---")
        df = pd.DataFrame(data)
        df.columns = ['id', 'text']
        df['id'] = df['id'].astype(str)
        df['text'] = df['text'].str.strip()
        
        tweet_lookup = pd.Series(df.text.values, index=df.id).to_dict()
        tweet_ids = df['id'].tolist()

        # Update cache
        _cache = {'tweet_lookup': tweet_lookup, 'tweet_ids': tweet_ids}
        _cache_time = time.time()

        return tweet_lookup, tweet_ids
    except Exception as e:
        print(f"!!! CRITICAL ERROR in get_sheets_data: {e}")
        return {}, []

@app.route('/')
def index():
    print("--- INDEX ROUTE HIT ---")
    tweet_lookup, tweet_ids = get_sheets_data()

    if len(tweet_ids) < 2:
        print("--- Not enough tweet IDs found, showing error page. ---")
        return "Not enough tweets to compare. Please check your Google Sheet."
    
    id1, id2 = random.sample(tweet_ids, 2)
    tweet1 = {'id': id1, 'text': tweet_lookup.get(id1, "Tweet text not found.")}
    tweet2 = {'id': id2, 'text': tweet_lookup.get(id2, "Tweet text not found.")}
    return render_template('index.html', tweet1=tweet1, tweet2=tweet2)

@app.route('/test')
def test():
    print("--- TEST ROUTE HIT ---")
    return "This is the test page. If you can see this, the Python function is running!"

@app.route('/vote', methods=['POST'])
def vote():
    winner_id = request.form['winner']
    loser_id = request.form['loser']
    
    client = get_google_sheets_client()
    if client:
        try:
            sheet = client.open("HotOrNotTweets").worksheet("Votes")
            # New format: id1, id2, result (winner_id)
            sheet.append_row([winner_id, loser_id, winner_id])
        except Exception as e:
            print(f"Error writing to sheet: {e}")
            
    return redirect(url_for('index'))

@app.route('/tie', methods=['POST'])
def tie():
    tweet1_id = request.form['tweet1']
    tweet2_id = request.form['tweet2']

    client = get_google_sheets_client()
    if client:
        try:
            sheet = client.open("HotOrNotTweets").worksheet("Votes")
            # New format: id1, id2, result ('tie')
            sheet.append_row([tweet1_id, tweet2_id, 'tie'])
        except Exception as e:
            print(f"Error writing tie to sheet: {e}")

    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    scores, pairwise_wins = {}, {}
    client = get_google_sheets_client()
    if client:
        try:
            sheet = client.open("HotOrNotTweets").worksheet("Votes")
            votes_data = sheet.get_all_records() # Use get_all_records for header mapping
            
            if votes_data:
                votes_df = pd.DataFrame(votes_data)
                # Filter out ties, count only explicit wins
                wins_df = votes_df[votes_df['result'] != 'tie']
                scores = wins_df['result'].value_counts().to_dict()

                # Adjust pairwise wins to handle new structure
                pairwise_wins = {}
                for index, row in wins_df.iterrows():
                    winner = row['result']
                    loser = row['id1'] if row['id2'] == winner else row['id2']
                    if winner not in pairwise_wins:
                        pairwise_wins[winner] = []
                    pairwise_wins[winner].append(loser)

        except Exception as e:
            print(f"Error reading votes from sheet: {e}")

    sorted_tweets = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    return render_template('admin.html', scores=sorted_tweets, pairwise_wins=pairwise_wins)

if __name__ == '__main__':
    app.run(debug=True) 
