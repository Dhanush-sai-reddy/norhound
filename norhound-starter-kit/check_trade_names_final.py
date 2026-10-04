import json
import urllib.request

for page in range(0, 3):
    url = f'https://data.brreg.no/enhetsregisteret/api/enheter?page={page}&size=1000'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NorHound/1.0'})
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            if '_embedded' in data and 'enheter' in data['_embedded']:
                items = data['_embedded']['enheter']
                for item in items:
                    forretningsnavn = item.get('forretningsnavn', 'INGEN')
                    if forretningsnavn and forretningsnavn != 'INGEN' and forretningsnavn != 'None' and forretningsnavn != 'None':
                        navn = item.get('navn', 'N/A')
                        orgnr = item.get('organisasjonsnummer', 'N/A')
                        print(f'{item.get("organisasjonsnummer", "N/A")}: {item.get("navn", "N/A")} | Forretningsnavn: {item.get("forretningsnavn")}')
except Exception as e:
    print(f'Error on page: {e}')