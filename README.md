# Log extractor

    usage: extract.py [-h] [--req] [--resp] [--filter FILTER] [--res-ok] [--res-nok] filename

#### positional arguments:
    
    filename         Path to logfile

#### optional arguments:
    -h, --help       Show this help message and exit
    --req            Include request
    --resp           Include response
    --filter FILTER  Unix-Shell wildcard string to filter blocks example:
                     '*"Method": "POST"*'
    --res-ok         Include successful requests
    --res-nok        Include failed requests