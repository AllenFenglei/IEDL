#python3 topic_cohe_corpus.py
#generate corpus for topic coherence detection
import xml.etree.ElementTree as ET
import codecs
import re
import nltk
from nltk import pos_tag
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet
from sklearn.feature_extraction.text import CountVectorizer
lemmatizer=WordNetLemmatizer()
from nltk.tokenize import TweetTokenizer
tknzr = TweetTokenizer()

ID_title = {}

def get_wordnet_pos(treebank_tag):
	if treebank_tag.startswith('J'):
		return wordnet.ADJ
	elif treebank_tag.startswith('V'):
		return wordnet.VERB
	elif treebank_tag.startswith('N'):
		return wordnet.NOUN
	elif treebank_tag.startswith('R'):
		return wordnet.ADV
	else:
		return None


def extract(filename):
	tree = ET.parse('./rawdata/'+filename+'.xml')
	root = tree.getroot()
	out = codecs.open('../../topic_cohe/ref_corpus/post/corpus.0', 'w', 'utf-8')
	count = 0
	
	for child in root:
		if filename == 'Comments':
			X = child.attrib.get('Text')
		elif filename == 'Posts':
			X = child.attrib.get('Body')
		score = child.attrib.get('Score')	#may have number smaller than 0
		time = child.attrib.get('CreationDate')
		title = child.attrib.get('Title')
		ID = child.attrib.get('Id')
		ParentID = child.attrib.get('ParentId')
		
		X = re.sub('(\r\n)+',' ',X);
		X = re.sub('(\n)+',' ',X);
		X = re.sub('<a href=((?!</a>).)*>',' ',X)
		X = re.sub('</a>','',X)
		X = re.sub('(<url> )+','<url> ',X)
		X = re.sub('<Br>|<br>','',X)
		X = re.sub('<br/>|<br />','',X)
		X = re.sub('<hr>|<hr />','',X)
		X = re.sub('<em>|</em>|<strong>|</strong>','',X)
		X = re.sub('<h1>|<h2>|<h3>|</h1>|</h2>|</h3>','',X)
		X = re.sub('<li>|</li>|<ul>|</ul>|<ol>|</ol>|<blockquote>|</blockquote>','',X)
		X = re.sub('<ol start=".">','',X)
		X = re.sub('<code>((?!</code>).)*</code>','',X)
	#	X = re.sub('<code>|</code>','',X)
		X = re.sub('<p>|</p>','',X)
		#X = re.sub('_________________________________________________________________|=================================================================','',X)
		X = re.sub('<pre>|</pre>','',X)	
		X = re.sub('<img((?!>).)*>', '',X)
		X = re.sub('(https?|ftp|file)://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]', ' ', X)


		X = X[:-1]
		X = re.sub(' +', ' ',X)
		if ID == "2562":
			X = "I wonder why it is tried to prove that, under no valid or not-ununcheckable conditions, it is said that it is absolutely impossible for an artificial intelligence system or collection of relative exclusive modules to involuntarily acquire more sophisticated capabilities in terms of generic cleverness of states of inclusive independency than its own developer. Thanks."

		#adding this part reduce the performance dynamiclly
		text = tknzr.tokenize(X.lower())
		#text = CountVectorizer().build_tokenizer()(X.lower())
		text_stem = []
		for w, p in pos_tag(text):
			wordnet_pos = get_wordnet_pos(p) or wordnet.NOUN
			text_stem.append(lemmatizer.lemmatize(w, pos=wordnet_pos))
		X = ' '.join(text_stem)
		#print(X)

		version = 0
		if time[8:10] == "2016":
			version = 0
		elif time[8:10] == "2017":
			version = 12
		else:
			version = 24

		if X != "":
			if time[5:7] == "01":
				out_time = "Jan "
				version = version + 1
			elif time[5:7] == "02":
				out_time = "Feb "
				version = version + 2
			elif time[5:7] == "03":
				out_time = "Mar "
				version = version + 3
			elif time[5:7] == "04":
				out_time = "Apr "
				version = version + 4
			elif time[5:7] == "05":
				out_time = "May "
				version = version + 5
			elif time[5:7] == "06":
				out_time = "Jun "
				version = version + 6
			elif time[5:7] == "07":
				out_time = "Jul "
				version = version + 7
			elif time[5:7] == "08":
				out_time = "Aug "
				version = version + 8
			elif time[5:7] == "09":
				out_time = "Sep "
				version = version + 9
			elif time[5:7] == "10":
				out_time = "Oct "
				version = version + 10
			elif time[5:7] == "11":
				out_time = "Nov "
				version = version + 11
			else:
				out_time = "Feb "
				version = version + 12
			out_time = out_time + time[8:10] + ", " + time[0:4]
			if title !=  None:
				ID_title[ID] = title
				out_title = title
			else:
				if ParentID != None:
					out_title = ID_title[ParentID]
				else:
					out_title = "None"
			
		
			if version < 36 and X != " ":
				out.write(X+'\n')
				count = count + 1

#extract('Comments')
extract('Posts')
