import google.generativeai as genai
import json

API_KEY = "AIzaSyCjGuA76vYJsp20naJ8NqwyO04nhOwScYs"

def google_ai (data):

    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f'''
            Ok, so i own a business where we do frequent transaction with high profile clients using crypto wallets, i have a program that
            gives me analysis of wallet.
            This data is essential to ensure safety of my business that am dealing with a proper client.
            Talk in third person. 
            Your existing responses are extremely salty, be rational and pragmatic. It can not be always money laundering, sometimes, it is actual transaction.
            I have given you a list of wallet trees who they dealt with having top 2 recent transactions from them.
            Give me analysis of this data in 5 lines as a suggestion to whether doing business with this wallet is safe or not.
            Point out the red flags. if the address starts with 0x it is from ERC20 chain and if it starts with T, it is from TRON chain
            donot suggest me to do further analysis and stuff as this is the data we got. say your opinion out loud do not tell us to do further analysis. You analyze and suggest your opinion. 
            \n\n
            {data}
    '''

    response = model.generate_content(prompt)

    return response.text