#!/usr/bin/env python2
import os, glob, sys, json, signal, logging, logging.handlers, MySQLdb, argparse, datetime
import pyodbc
import pycurl
import csv
from StringIO import StringIO

DEST_PATH = '/etc/phonebook/destination-import.json'

def signalHandler(sig, frame):
  logger.critical('interrupted by SIGINT')
  sys.exit(0)

signal.signal(signal.SIGINT, signalHandler)

def getDbConn(config):
  if config['dbtype'] == 'mysql':
    port = unixSocket = None
    try:
      port = int(config['port'])
    except:
      port = None
      unixSocket = config['port']
    try:
      if port:
        return MySQLdb.connect(host=config['host'], port=port, user=config['user'], passwd=config['password'], db=config['dbname'])
      else:
        return MySQLdb.connect(host=config['host'], unix_socket=unixSocket, user=config['user'], passwd=config['password'], db=config['dbname'])
    except Exception as err:
      logger.error(str(err))
      return None
  elif(config['dbtype'] == 'mssql'):
    port = unixSocket = None
    try:
      port = int(config['port'])
    except:
      port = None
      unixSocket = config['port']
    try:
      if port:
        return pyodbc.connect(driver=config['driver'], server=config['host'], port=port, uid=config['user'], pwd=config['password'], database=config['dbname'])
      else:
        return pyodbc.connect(driver=config['driver'], server=config['host'], unix_socket=unixSocket, uid=config['user'], pwd=config['password'], database=config['dbname'])
    except Exception as err:
      logger.error(str(err))
      return None

def syncSourceMysql(path, output, deleteonly):
  with open(path, 'r') as sourceFile:
    sConfig = json.load(sourceFile)
  sid = next(iter(sConfig))
  dbSource = getDbConn(sConfig[sid])
  if output == True:
    if(sConfig[sid]['dbtype'] == 'mysql'):
    	dbSource.set_character_set('utf8') # questa funzione non esiste per pyodbc https://github.com/mkleehammer/pyodbc/wiki/Unicode
    if(sConfig[sid]['dbtype'] == 'mssql'):
   	dbSource.setdecoding(pyodbc.SQL_WMETADATA, encoding='utf-32le')
  if dbSource != None:
    logger.debug('source "' + sid + '" connection (' + sConfig[sid]['dbname'] + '): ok')
  else:
    logger.error('source "' + sid + '" connection (' + sConfig[sid]['dbname'] + '): failed')
    sys.exit(1)
  curSource = dbSource.cursor()
  if output == True:
    curSource.execute(sConfig[sid]['query'])
    rows = curSource.fetchall()
    cols = tuple([i[0] for i in curSource.description])
    res = []
    for row in rows:
      temp = {}
      for i, el in enumerate(row):
        temp[cols[i]] = el
      res.append(temp)
    if len(res) == 0:
      temp = {}
      for x in cols:
        temp[x] = ''
      res.append(temp)
    json.dump(res, sys.stdout)
    logger.info('write ' + str(len(rows)) + ' entries to std output')
    logger.info('end ' + ('check of' if output == True else '') + ' source import of ' + path + ' into phonebook.phonebook')
    curSource.close()
    dbSource.close()
    return
  try:
    with open(DEST_PATH, 'r') as configFile:
      dConfig = json.load(configFile)
  except Exception as err:
    logger.error('reading ' + DEST_PATH)
    logger.error(str(err))
    sys.exit(1)
  dbDest = getDbConn(dConfig)
  if dbDest != None:
    logger.debug('destination db connection ("phonebook"): ok')
  else:
    logger.error('destination db connection ("phonebook"): failed')
    sys.exit(1)
  curDest = dbDest.cursor()
  try:
    delcount = curDest.execute('DELETE FROM ' + dConfig['dbtable'] + ' WHERE sid_imported="{}"'.format(sid))
    logger.info('clean destination: removed ' + str(delcount) + ' entries from ' + dConfig['dbname'] + '.' + dConfig['dbtable'] + ' with sid_imported="' + sid + '"')
    if deleteonly == True:
      return
  except Exception as err:
    logger.error('cleaning destination: removing entries from ' + dConfig['dbname'] + '.' + dConfig['dbtable'] + ' with sid_imported="' + sid + '"')
    logger.error(str(err))
  curSource.execute(sConfig[sid]['query'])
  toTransfer = curSource.rowcount
  logger.debug('synchronizing source "' + sid + '" (' + str(toTransfer) + ' entries)...')
  start = datetime.datetime.now().replace(microsecond=0)
  sourceCols = sConfig[sid]['mapping'].keys()
  destCols = sConfig[sid]['mapping'].values()
  destCols.append('sid_imported')
  if(sConfig[sid]['dbtype'] == 'mysql'):
    curSource = dbSource.cursor(MySQLdb.cursors.DictCursor)
    curSource.execute(sConfig[sid]['query'])
    row=curSource.fetchnone()
    importedCount=0
    errCount=0

  elif(sConfig[sid]['dbtype'] == 'mssql'):
    result=[]
    curSource = pyodbc.cursor()
    curSource.execute(sConfig[sid]['query'])
   # columns = [column[0] for column in curSource.description] # sourceCols contiene gia' la lista delle colonne sorgente, a cosa serve questo codice? Va bene copiare codice, ma devio capire cosa fa e perche'
   # for row in curSource.fetchall(): # questo codice funziona, ma mi sembra incollato qui a cazzo di cane.
   #	x = dict(zip(columns, row) ) # perche' le metti in un dict?
   #	result.append(x) # popoli la variabile result e poi non ci fai nulla
    row = curSource.fetchone() # perche' ora rileggi la riga? va bene, ma elimina il codice qui sopra
    importedCount = 0
    errCount = 0
  
  
  
  if sConfig[sid]['type'] != None:
    destCols.append('type')
  percents = ('%s, ' * len(destCols))[:-2]
  while row is not None:
    values = []
    for el in sourceCols:
      if(sConfig[sid]['dbtype'] == 'mysql'):
	values.append(row[el]) # non puoi accedere ad un oggetto di tipo row du pyodbc come fosse un dict, puoi usare __getattribute__ https://github.com/mkleehammer/pyodbc/wiki/Row
      elif(sConfig[sid]['dbtype'] == 'mssql'):
	row.__getattribute__('el')
    values.append(str(sid))
    if sConfig[sid]['type'] != None:
      values.append(str(sConfig[sid]['type']))
    sql = 'INSERT INTO ' + dConfig['dbtable'] + ' (' + ','.join(destCols) + ') VALUES (' + percents + ')'
    try:
      curDest.execute(sql, tuple(values))
      importedCount += 1
    except Exception as err:
      errCount += 1
      logger.error('copying entry "' + str(row) + '"')
      logger.error(str(err))
    dbDest.commit()
    row = curSource.fetchone()
  end = datetime.datetime.now().replace(microsecond=0)
  percent = str(importedCount*100/toTransfer) if toTransfer > 0 else '0'
  logger.info('source "' + sid + '" imported ' + percent + '%: ' + str(importedCount) + ' imported - ' + str(errCount) + ' errors - ' + str(toTransfer) + ' tot - duration ' + str(end-start))
  curSource.close()
  curDest.close()
  dbSource.close()
  dbDest.close()
  logger.info('end source import of ' + path + ' into phonebook.phonebook')

def extractArgsDbParams(data):
  result = {}
  for arg in data:
    result[arg.split('=')[0]] = arg.split('=')[1]
  return result

def syncSourceCsv(path, output, deleteonly):
  with open(path, 'r') as sourceFile:
    sConfig = json.load(sourceFile)

  sid = next(iter(sConfig))
  crl = pycurl.Curl()

  crl.setopt(crl.URL,  str(sConfig[sid]['url']))

  b_obj = StringIO()
  crl.setopt(crl.WRITEFUNCTION, b_obj.write)

  crl.setopt(crl.FAILONERROR, 1)
  crl.setopt(crl.FOLLOWLOCATION, 1)
  crl.setopt(crl.MAXREDIRS, 5)

  try:
    crl.perform()
    logger.debug('source "' + sid + '" connection (' + sConfig[sid]['url'] + '): ok')
  except Exception as err:
    logger.error('source "' + sid + '" connection (' + sConfig[sid]['url'] + '): failed')
    logger.error(str(err))
    sys.exit(1)
  finally:
    crl.close()

  b_obj.seek(0)

  df = []
  sample = b_obj.read(1024)
  b_obj.seek(0)
  dialect = csv.Sniffer().sniff(sample)
  if (not csv.Sniffer().has_header(sample)):
    logger.warn('CSV doesn\'t have a valid header!')
  csvr = csv.reader(b_obj, dialect=dialect)
  header = next(csvr, None)
  for row in csvr:
    r = {}
    for idx,item in enumerate(row):
        r[header[idx]] = item
    df.append(r)

  if output == True:
    json.dump(df, sys.stdout)
    logger.info('end ' + ('check of' if output == True else '') + ' source import of ' + path + ' into phonebook.phonebook')
    return

  try:
    with open(DEST_PATH, 'r') as configFile:
      dConfig = json.load(configFile)
  except Exception as err:
    logger.error('reading ' + DEST_PATH)
    logger.error(str(err))
    sys.exit(1)
  dbDest = getDbConn(dConfig)
  if dbDest != None:
    logger.debug('destination db connection ("phonebook"): ok')
  else:
    logger.error('destination db connection ("phonebook"): failed')
    sys.exit(1)

  curDest = dbDest.cursor()

  try:
    delcount = curDest.execute('DELETE FROM ' + dConfig['dbtable'] + ' WHERE sid_imported="{}"'.format(sid))
    logger.info('clean destination: removed ' + str(delcount) + ' entries from ' + dConfig['dbname'] + '.' + dConfig['dbtable'] + ' with sid_imported="' + sid + '"')
    if deleteonly == True:
      return
  except Exception as err:
    logger.error('cleaning destination: removing entries from ' + dConfig['dbname'] + '.' + dConfig['dbtable'] + ' with sid_imported="' + sid + '"')
    logger.error(str(err))

  toTransfer = len(df)

  logger.debug('synchronizing source "' + sid + '" (' + str(toTransfer) + ' entries)...')

  start = datetime.datetime.now().replace(microsecond=0)

  sourceCols = sConfig[sid]['mapping'].keys()
  destCols = sConfig[sid]['mapping'].values()
  destCols.append('sid_imported')

  if sConfig[sid]['type'] != None:
    destCols.append('type')

  importedCount = 0
  errCount = 0

  percents = ('%s, ' * len(destCols))[:-2]
  for row in df:
    values = []
    for el in sourceCols:
      values.append(row[el.encode('utf-8')].decode('utf-8'))
    values.append(str(sid))
    if sConfig[sid]['type'] != None:
      values.append(str(sConfig[sid]['type']))
    sql = 'INSERT INTO ' + dConfig['dbtable'] + ' (' + ','.join(destCols) + ') VALUES (' + percents + ')'
    try:
      curDest.execute(sql, tuple(values))
      importedCount += 1
    except Exception as err:
      errCount += 1
      logger.error('copying entry "' + str(row) + '"')
      logger.error(str(err))
    dbDest.commit()
  end = datetime.datetime.now().replace(microsecond=0)
  percent = str(importedCount*100/toTransfer) if toTransfer > 0 else '0'
  logger.info('source "' + sid + '" imported ' + percent + '%: ' + str(importedCount) + ' imported - ' + str(errCount) + ' errors - ' + str(toTransfer) + ' tot - duration ' + str(end-start))
  curDest.close()
  dbDest.close()
  logger.info('end source import of ' + path + ' into phonebook.phonebook')

if __name__ == '__main__':
  descr = 'MySQL and CSV Phonebook importer. Imports contacts from a MySQL database (or CSV) source into phonebook.phonebook database. The destination configuration data is into the /etc/phonebook/destination-import.json file. Destination log is syslog.'
  parser = argparse.ArgumentParser(description=descr)
  parser.add_argument('source_path', help='absolute path of the source json configuration file')
  parser.add_argument('-lw', '--log_warning', action='store_true', help='enable only warning log messages in syslog')
  parser.add_argument('-lv', '--log_verbose', action='store_true', help='enable debug log level in syslog')
  parser.add_argument('-v', '--verbose', action='store_true', help='enable console debug')
  parser.add_argument('-c', '--check', action='store_true', help='it causes the writing of query results to standard output in JSON format instead of executing the database synchronization. Has more priority than deleteonly')
  parser.add_argument('-d', '--deleteonly', action='store_true', help='just delete entries from this configuration')
  args = parser.parse_args()
  logger = logging.getLogger(__name__)
  logger.setLevel(logging.DEBUG)
  cHandler = logging.StreamHandler()
  syslogHandler = logging.handlers.SysLogHandler(address = '/dev/log')
  cHandler.setLevel(logging.DEBUG if args.verbose == True else logging.NOTSET)
  syslogHandler.setLevel(logging.INFO if args.log_warning == False else logging.WARNING)
  logFormat = logging.Formatter('[%(process)s] %(levelname)s: %(message)s', datefmt='%d-%b-%y %H:%M:%S')
  cHandler.setFormatter(logFormat)
  syslogHandler.setFormatter(logFormat)
  if args.verbose == True:
    logger.addHandler(cHandler)
  logger.addHandler(syslogHandler)
  if args.source_path:
    logger.info('start ' + ('check of' if args.check == True else '') + ' source import of ' + args.source_path + ' into phonebook.phonebook')
    try:
      logger.debug('reading ' + args.source_path)
      with open(args.source_path, 'r') as sourceFile:
        sConfig = json.load(sourceFile)
	print("CARICAMENTO RIUSCITO") # Togliere
    except Exception as err:
      logger.error('reading ' + args.source_path)
      logger.error(str(err))
      sys.exit(1)
    sid = next(iter(sConfig))
    logger.debug(args.source_path + ' has "' + sid + '" source')
    if not sConfig[sid]['enabled']:
      logger.info(sid + ' is disabled')
      sys.exit(0)
    if sConfig[sid]['dbtype'] == 'mysql': # In questo modo chiama la funzione syncSourceMysql solo se il dbtype e mysql, se lo metti a mssql non entra mai nella funzione con il tuo codice. O crei un'altra funzione con il tuo codice e la chiami se il db type e' mssql o cambi questo if 
      syncSourceMysql(args.source_path, args.check, args.deleteonly)
    elif sConfig[sid]['dbtype'] == 'mssql':
      syncSourceMysql(args.source_path, args.check, args.deleteonly)
    elif sConfig[sid]['dbtype'] == 'csv':
      syncSourceCsv(args.source_path, args.check, args.deleteonly)
  else:
    parser.print_help()
