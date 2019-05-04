#!/bin/bash

#main="main.py"
#main_doc_level="main_doc_level.py"
#main_add_views="main_add_views.py"

if [[ $1 ==  'normal' ]]; then
	echo "Using orgin interpretation approach..."
	python main.py
	../topic_cohe/run-oc.sh
elif [[ $1 ==  'test' ]]; then
	echo "Testing by manually labeled data..."
	python main_doc_level.py
	#../topic_cohe/run-oc.sh
elif [[ $1 ==  'views' ]]; then
	echo "Using new interpretation approach with views attribute..."
	python main_add_views.py
	../topic_cohe/run-oc.sh
else
	echo "Please enter './run normal(or test or views)'"
fi

