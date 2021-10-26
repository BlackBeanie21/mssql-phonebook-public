import pyodbc


connection = "DRIVER={ODBC Driver for SQL Server 2.3.6};SERVER=192.168.5.43;PORT=1433;DATABASE=master;UID=sa;PWD=Raffaele,1234"

try:
	conn = pyodbc.connect(connection) 
	print("CONNESSIONE RIUSCITA")
except:
	print("NADA")

