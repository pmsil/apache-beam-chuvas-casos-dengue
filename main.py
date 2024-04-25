import re
import apache_beam as beam
from apache_beam.io import ReadFromText
from apache_beam.io.textio import WriteToText
from apache_beam.options.pipeline_options import PipelineOptions

pipeline_options = PipelineOptions(argv=None)
pipeline = beam.Pipeline(options=pipeline_options)

colunas_dengue = ['id',
                  'data_iniSE',
                  'casos',
                  'ibge_code',
                  'cidade',
                  'uf',
                  'cep',
                  'latitude',
                  'longitude']


def texto_para_lista(elemento, delimitador='|'):
    """
    Recebe um texto e um delimitador 
    Retorna uma lista de elementos pelo delimitador
    """
    return elemento.split(delimitador)


def lista_para_dicionario(elemento, colunas):
    """
    Recebe 2 listas
    Retorna 1 dicionário
    """
    return dict(zip(colunas, elemento))

def trata_datas(elemento):
    """
    Recebe um dicionário e cria um novo campo com ANO-MES
    Retorna o mesmo dicionário com o novo campo
    """
    elemento['ano_mes'] = '-'.join(elemento['data_iniSE'].split('-')[:2])
    return elemento

def chave_uf (elemento):
    """
    Recebe um dicionário
    Retorna uma tupla com o estado (UF) e o elemento (UF, dicionario)
    """
    chave = elemento['uf']
    return (chave, elemento)

def casos_dengue(elemento):
    """
    Recebe uma tupla ('UF',[{},{}])
    Retorna uma tupla ('UF', 'casos')
    """
    uf, registros = elemento
    for registro in registros:
        if(bool(re.search(r'\d', registro['casos']))):
            yield (f"{uf}-{registro['ano_mes']}", float(registro['casos']))
        else:
            yield (f"{uf}-{registro['ano_mes']}", 0.0)

def chave_uf_ano_mes_de_lista(elemento):
    """
    Receber uma lista de elementos
    Retornar uma tupla contendo uma chave e o valor de chuva em mm ('UF-ANO-MES','1.3')
    """
    data, mm, uf = elemento
    ano_mes = '-'.join(data.split('-')[:2])
    chave = f'{uf}-{ano_mes}'
    if float(mm) < 0:
        mm = 0.0
    else:
        mm = float(mm)
    return chave, mm

def arredonda(elemento):
    """
    Recebe uma tupla ('MG-2015-04', 3812.9999999999486)
    Retorna uma tupla com o valor arredondado ('MG-2015-04', 3813.0)
    """
    chave, mm = elemento
    return (chave, round(mm,1))

def filtra_campos_vazios(elemento):
    """
    Remove elementos que tenham chaves vazias
    Receber uma tupla ('CE-2015-10', {'chuvas': [0.0], 'dengue': []})
    caso ela possua um dos campos vazios ela não será retornada
    """
    chave, dados = elemento
    if all([
        dados['chuvas'],
        dados['dengue']
        ]):
        return True
    return False

def descompactar_elementos(elemento):
    """
    Receber uma tupla ('CE-2015-12', {'chuvas': [7.6], 'dengue': [29.0]})
    Retornar uma tupla ('CE','2015','12','7.6','29.0')
    """
    chave, dados = elemento
    chuva = dados['chuvas'][0]
    dengue = dados['dengue'][0]
    uf, ano, mes = chave.split('-')
    return uf, ano, mes, str(chuva), str(dengue)

def preparar_csv(elemento, delimitador=';'):
    """
    Receber uma tupla ('CE', '2015', '12', '7.6', '29.0')
    retornar uma string demitada "CE, 2015, 12, 7.6, 29.0"
    """
    return f"{delimitador}".join(elemento)


dengue = (
    pipeline
    | "Leitura do dataset de dengue" >> 
        ReadFromText('casos_dengue.txt', skip_header_lines=1)
       # ReadFromText('sample_casos_dengue.txt', skip_header_lines=1)
    | "De texto para lista" >> beam.Map(texto_para_lista)
    | "De lista para dicionário" >> beam.Map(lista_para_dicionario, colunas_dengue)
    | "Criar campo ano_mes" >> beam.Map(trata_datas)
    | "Criar chave pelo estado" >> beam.Map(chave_uf)
    | "Agrupar pelo estado" >> beam.GroupByKey()
    | "Descompactar casos de dengue" >> beam.FlatMap(casos_dengue)
    | "Soma dos casos de dengue pela chave" >> beam.CombinePerKey(sum)
    #| "Mostrar resultados" >> beam.Map(print)

)

chuvas = (
    pipeline
    | "Leitura do dataset de chuvas" >> 
        ReadFromText('chuvas.csv', skip_header_lines=1)
        #ReadFromText('sample_chuvas.csv', skip_header_lines=1)
    | "De texto para lista (chuvas)" >> beam.Map(texto_para_lista, delimitador=',')        
    | "Criando a chave UF-ANO-MES" >> beam.Map(chave_uf_ano_mes_de_lista)
    | "Soma do total de chuvas pela chave" >> beam.CombinePerKey(sum)
    | "Arredondar resultados de chuvas" >> beam.Map(arredonda)
    #| "Mostrar resultados de chuvas" >> beam.Map(print)
)



resultado = (
    #(chuvas, dengue)
    #| "Empilha as pcollections" >> beam.Flatten()
    #| "Agrupa as pcollections" >> beam.GroupByKey()
    ({'chuvas':chuvas, 'dengue':dengue})
    | "Mesclar pcollections" >> beam.CoGroupByKey()
    | "Filtrar dados vazios" >> beam.Filter(filtra_campos_vazios)
    | "Descompactar elementos" >> beam.Map(descompactar_elementos)
    | "Preparar CSV" >> beam.Map(preparar_csv)
    # | "Mostrar resultados da união" >> beam.Map(print)

 )

header='UF;ANO;MES;CHUVA;DENGUE'
resultado | 'Criar arquivo CSV' >> WriteToText('resultado',file_name_suffix='.csv',header=header)

pipeline.run()