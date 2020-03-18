from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import *


@api_view()
def snapshot_get_value(request):
    address = request.query_params['address']
    if request.query_params['blockchain'] == 'eth':
        try:
            return Response({'result': str(SnapshotRow.objects.get(eth_address=address.lower()).value)})
        except:
            return Response({'result': 0})
    elif request.query_params['blockchain'] == 'eos':
        try:
            return Response({'result': str(SnapshotEOSRow.objects.get(eos_address=address).value)})
        except:
            return Response({'result': 0})
    else:
       return Response({'result': 0})
