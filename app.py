from flask import Flask, render_template, request, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import random
import os
import json

app = Flask(__name__)

# --- Google Sheets Setup ---
def get_google_sheets_client():
    """Establishes connection with Google Sheets."""
    try:
        creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
        creds_dict = json.loads(creds_json)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return None

def get_sheets_data():
    """Fetches and processes data from Google Sheets."""
    client = get_google_sheets_client()
    if not client:
        return {}, []

    try:
        sheet = client.open("HotOrNotTweets").worksheet("Tweets")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        df.columns = ['id', 'text']
        df['id'] = df['id'].astype(str)
        df['text'] = df['text'].str.strip()
        
        tweet_lookup = pd.Series(df.text.values, index=df.id).to_dict()
        tweet_ids = df['id'].tolist()
        return tweet_lookup, tweet_ids
    except gspread.exceptions.SpreadsheetNotFound:
        print("Spreadsheet 'HotOrNotTweets' not found.")
        return {}, []
    except gspread.exceptions.WorksheetNotFound:
        print("Worksheet 'Tweets' not found.")
        return {}, []
    except Exception as e:
        print(f"Error getting data from sheet: {e}")
        return {}, []

tweet_lookup, tweet_ids = get_sheets_data()

@app.route('/')
def index():
    if len(tweet_ids) < 2:
        return "Not enough tweets to compare. Please check your Google Sheet."
    
    id1, id2 = random.sample(tweet_ids, 2)
    tweet1 = {'id': id1, 'text': tweet_lookup.get(id1, "Tweet text not found.")}
    tweet2 = {'id': id2, 'text': tweet_lookup.get(id2, "Tweet text not found.")}
    return render_template('index.html', tweet1=tweet1, tweet2=tweet2)

@app.route('/vote', methods=['POST'])
def vote():
    winner_id = request.form['winner']
    loser_id = request.form['loser']
    
    client = get_google_sheets_client()
    if client:
        try:
            sheet = client.open("HotOrNotTweets").worksheet("Votes")
            sheet.append_row([winner_id, loser_id])
        except Exception as e:
            print(f"Error writing to sheet: {e}")
            
    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    scores, pairwise_wins = {}, {}
    client = get_google_sheets_client()
    if client:
        try:
            sheet = client.open("HotOrNotTweets").worksheet("Votes")
            votes = sheet.get_all_values()
            
            if votes:
                votes_df = pd.DataFrame(votes, columns=['winner', 'loser'])
                scores = votes_df['winner'].value_counts().to_dict()
                pairwise_wins = votes_df.groupby('winner')['loser'].apply(list).to_dict()

        except Exception as e:
            print(f"Error reading votes from sheet: {e}")

    sorted_tweets = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    return render_template('admin.html', scores=sorted_tweets, pairwise_wins=pairwise_wins)

if __name__ == '__main__':
    app.run(debug=True) 
