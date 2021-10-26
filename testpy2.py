import pyodbc as p
try:
	conn = p.connect("driver={ODBC Driver 17 for SQL Server};server=192.168.5.56;port=1433;database=master;uid=sa;pwd=Raffaele,1234")
	print("AAAAA")
except:
	print("BBBBBB")


