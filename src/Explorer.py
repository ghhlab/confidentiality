import design
from PyQt5.QtWidgets import QApplication, QMainWindow,QFileDialog
from PyQt5.QtCore import QUrl
from PyQt5 import QtWebKit
import os
import sys
from PyQt5.QtCore import pyqtSlot
from fiona.crs import to_string,from_epsg
from scipy.spatial import cKDTree
import numpy as np
import fiona
import random
import copy
import datetime
from keys import *
from osgeo import osr,ogr,gdal
from osgeo import gdal_array
xoffset=[1000000,5000000]
#yoffset=[0,37614428]
yoffset=[100000,600000]
x_max=19926188.85
y_max=18807214.10
ref4326=osr.SpatialReference()
ref4326.ImportFromEPSG(4326)
ref3857=osr.SpatialReference()
ref3857.ImportFromEPSG(3857)
transf3857to4326=osr.CoordinateTransformation(ref3857, ref4326)
def checkGeographicalCoordinates(x,y):
    return x>=-180 and x<=180 and y>=-90 and y<=90

# example GDAL error handler function
def gdal_error_handler(err_class, err_num, err_msg):
    errtype = {
            gdal.CE_None:'None',
            gdal.CE_Debug:'Debug',
            gdal.CE_Warning:'Warning',
            gdal.CE_Failure:'Failure',
            gdal.CE_Fatal:'Fatal'
    }
    err_msg = err_msg.replace('\n',' ')
    err_class = errtype.get(err_class, 'None')
    print ('Error Number: %s' % (err_num))
    print ('Error Type: %s' % (err_class))
    print ('Error Message: %s' % (err_msg))

class Explorer(QMainWindow, design.Ui_MainWindow):
    def __init__(self, parent=None):
        super(Explorer, self).__init__(parent)
        self.setupUi(self)
        cwd = os.getcwd()
        self.webView.settings().setAttribute(QtWebKit.QWebSettings.PluginsEnabled, True)
        self.webView.load(QUrl('file:///'+cwd+'/working/Explorer.html'))
        self.webView.loadFinished.connect(self.finishLoading)
        self.currFile=None
        self.kdTree=None
        self.random=None
        self.epsg=None
        self.isGeographic=None
        self.units=None
        self.currProj=None
        self.outputfolder=None
    @pyqtSlot()
    def finishLoading(self):
        self.webView.page().mainFrame().addToJavaScriptWindowObject("exp", self)

    def clearVariables(self):
        self.currFile=None
        self.kdTree=None
        self.random=None
        self.currProj=None
        self.isGeographic=None

    def getKeyData(self,key):
        k=Keys.get(Keys.name == key)
        return k
        
    @pyqtSlot(str,str,result=str)
    def downloadTransformedRaster(self,newFname,key):
        dataobj={}
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Raster",
                '', "Raster File (*.tif *.TIF)")
        if not fileName or (not fileName.lower().endswith('tif')):
            dataobj['error']='Important file information missing'
            return json.dumps(dataobj)
        keydata=self.getKeyData(key)
        randomkey=keydata.keyval
        inpraster = gdal.Open(fileName)
        inpband=inpraster.GetRasterBand(1)
        transformvals=inpraster.GetGeoTransform()
        inpRef=osr.SpatialReference()
        inpRef.ImportFromWkt(inpraster.GetProjectionRef())
        coordTrans = osr.CoordinateTransformation(inpRef,ref3857)
        data=inpband.ReadAsArray()
        rotated_data=np.rot90(data,k=2)
        const_x=(randomkey*(xoffset[1]-xoffset[0])+xoffset[0])
        const_y=(randomkey*(yoffset[1]-yoffset[0])+yoffset[0])
        #do the rotation
        x_val=-transformvals[0]
        y_val=-transformvals[3]
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint(x_val,y_val)
        point.Transform(coordTrans)
        coords=[point.GetX(),point.GetY()]
        #do the translation
        new_x=coords[0]-const_x
        if new_x<-x_max:
            new_x=x_max-(-x_max-new_x)
        new_y=coords[1]-const_y
        if new_y<-y_max:
            new_y=y_max-(-y_max-new_y)
        new_y+=(-transformvals[5]*inpraster.RasterYSize)
        new_x-=(transformvals[1]*inpraster.RasterXSize)
        #we have to account for the rotation during transformation
        transbounds=list(map(float,keydata.transbounds.split(',')))
        y_change=np.abs((transbounds[-1]-transformvals[3])+(transbounds[1]-(transformvals[3]-(inpraster.RasterYSize*(-transformvals[5])))))
        x_change=np.abs((transbounds[0]-transformvals[0])+(transbounds[2]-(transformvals[0]+(inpraster.RasterXSize*transformvals[1]))))
        #check conditions crucial for methods were the newly formed raster is having smaller extent than the real data. Example Spline interpolation.
        ry,rx=float(y_change)/(-transformvals[5]),float(x_change)/transformvals[1]
        roll_y=int(np.ceil(ry))
        roll_x=int(np.ceil(rx))
        if roll_y-ry>.5:
            roll_y=int(ry)
        if roll_x-rx>.5:
            roll_x=int(rx)
        print (roll_y)
        print (roll_x)
        if transbounds[-1]>transformvals[3]:
            new_y+=y_change
            #rolling based on the ychange
            if roll_y!=0:
                rotated_data=np.roll(rotated_data,roll_y,axis=0)
        else:
            new_y-=y_change
            #rolling based on the ychange
            if roll_y!=0:
                rotated_data=np.roll(rotated_data,-roll_y,axis=0)
        if transbounds[0]>transformvals[0]:
            new_x+=x_change
            #rolling based on the xchange
            if roll_x!=0:
                rotated_data=np.roll(rotated_data,-roll_x,axis=1)
        else:
            new_x-=x_change
            #rolling based on the xchange
            if roll_x!=0:
                rotated_data=np.roll(rotated_data,roll_x,axis=1)
        driver = gdal.GetDriverByName('GTiff')
        outdir=self.outputfolder
        outRaster = driver.Create(outdir+'\\'+newFname+'.tif',inpraster.RasterXSize , inpraster.RasterYSize, 1, gdal_array.NumericTypeCodeToGDALTypeCode(data.dtype))
        outRaster.SetGeoTransform((new_x, transformvals[1], 0, new_y, 0, transformvals[5]))
        outband = outRaster.GetRasterBand(1)
        outband.WriteArray(rotated_data)
        if (inpband.GetNoDataValue() is not None):
            outband.SetNoDataValue(inpband.GetNoDataValue())
        outRaster.SetProjection(ref3857.ExportToWkt())
        outband.FlushCache()
        driver=outRaster=None
        return 'transformed raster successfully downloaded'
        
    @pyqtSlot(str,str,result=str)
    def downloadTransformedShape(self,newFname,key):
        dataobj={}
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Shape File",
                '', "Shape files (*.shp *.SHP)")
        if not fileName or (not fileName.lower().endswith('shp')):
            dataobj['error']='Important file information missing'
            return json.dumps(dataobj)
        randomkey=self.getKeyData(key).keyval
        driver=ogr.GetDriverByName("ESRI Shapefile")
        sourced=driver.Open(fileName)
        layer = sourced.GetLayer()
        spatialRef = layer.GetSpatialRef()
        transf=osr.CoordinateTransformation(spatialRef, ref3857)
        driver=sourced=None
        with fiona.open(fileName) as src:
            schema=src.schema
            const_x=(randomkey*(xoffset[1]-xoffset[0])+xoffset[0])
            const_y=(randomkey*(yoffset[1]-yoffset[0])+yoffset[0])
            outdir=self.outputfolder
            with fiona.open(outdir+'\\'+newFname+'.shp','w',schema=schema,crs=from_epsg(3857),driver=src.driver) as sink:
                for elementary in src:
                    elem=copy.deepcopy(elementary)
                    coords=elem['geometry']['coordinates']
                    point = ogr.Geometry(ogr.wkbPoint)
                    point.AddPoint(elem['geometry']['coordinates'][0], elem['geometry']['coordinates'][1])
                    point.Transform(transf)
                    coords=[point.GetX(),point.GetY()]
                    #while re-converting first rotate and then translate
                    #perform rotation
                    new_coords_clockwise_rotation=[(-1)*coords[0],(-1)*coords[1]]
                    #then translate
                    new_x=new_coords_clockwise_rotation[0]-const_x
                    if new_x<-x_max:
                        new_x=x_max-(-x_max-new_x)
                    new_y=new_coords_clockwise_rotation[1]-const_y
                    if new_y<-y_max:
                        new_y=y_max-(-y_max-new_y)
                    elem['geometry']['coordinates']=(new_x,new_y)
                    sink.write(elem)
        return 'transformed file successfully downloaded'
    
    #upload data file and do all necessary checks
    @pyqtSlot(result=str)
    def uploadDataFile(self):
        self.clearVariables();
        dataobj={}
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Shape File",
                '', "Shape files (*.shp *.SHP)")
        if not fileName or (not fileName.lower().endswith('shp')):
            dataobj['error']='Important file information missing'
            return json.dumps(dataobj)
        epsg,isFionaIdentified=None,False        
        crs,source,source_schema,isGeographic,projstring,isPyProj=None,[],None,False,None,False
        projstring=None
        #open this file with fiona
        with fiona.open(fileName) as src:
            crs = src.crs
            source_schema = src.schema
            for dat in src:
                source.append(dat)
        if len(source)==0:
            dataobj['error']='Shape file has no data'
            return json.dumps(dataobj)
        if (source_schema['geometry']!='Point'):
            dataobj['error']='Only accpets point based shape files'
            return json.dumps(dataobj)
        #read a single record for tests
        rec=source[0]
        #if there is no prj file
        if crs is None or len(crs)==0:
            #if we are assuming these are geographical then type check to see whether they are in with limits
            if not checkGeographicalCoordinates(rec['geometry']['coordinates'][0],rec['geometry']['coordinates'][1]):
                dataobj['error']='Projection files are missing and the files doesnot seem to be in Geographic Coordinate Format'
                return json.dumps(dataobj)
            else:
                isGeographic=True
                self.currProj=osr.SpatialReference()
                self.currProj.ImportFromEPSG(4326)
        else:
            #check if we can 
            driver,sourced=None,None
            try:
                #get the proj string from file and check if we can do a conversion
                driver=ogr.GetDriverByName("ESRI Shapefile")
                sourced=driver.Open(fileName)
                layer = sourced.GetLayer()
                spatialRef = layer.GetSpatialRef()
                epsgRef=osr.SpatialReference()
                epsgRef.ImportFromEPSG(4326)
                point = ogr.Geometry(ogr.wkbPoint)
                point.AddPoint(rec['geometry']['coordinates'][0], rec['geometry']['coordinates'][1])
                coordTransform = osr.CoordinateTransformation(spatialRef, epsgRef)
                point.Transform(coordTransform)
                self.currProj=osr.SpatialReference(spatialRef.ExportToWkt())
                isGeographic=self.currProj.IsGeographic()
                driver=sourced=None
            except:
                driver=sourced=None
                dataobj['error']='Cannot identify the projection'
                return json.dumps(dataobj)
        #error checks completed ready for processing
        #create the linear unit based coordinates for kdtree (3857 meters)
        currDataInLinearUnits=[]
        dataindegree=[]
        metertransform=osr.CoordinateTransformation(self.currProj, ref3857)
        degreetransform=osr.CoordinateTransformation(self.currProj, ref4326)
        for recs in source:
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(recs['geometry']['coordinates'][0], recs['geometry']['coordinates'][1])
            point.Transform(metertransform)
            currDataInLinearUnits.append([point.GetX(),point.GetY()])
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(recs['geometry']['coordinates'][0], recs['geometry']['coordinates'][1])
            point.Transform(degreetransform)
            dataindegree.append([point.GetX(),point.GetY()])
        self.kdTree=cKDTree(currDataInLinearUnits)
        #once the geographical coordinates are created it can be send to front end for the map
        dataobj['coordinates']=dataindegree
        self.currFile=fileName
        self.isGeographic=isGeographic
        return json.dumps(dataobj)

    #accepts a random value a random value and return the transformed coordinates in meters
    def transformCoordinates(self,randv):
        const_x=(randv*(xoffset[1]-xoffset[0])+xoffset[0])
        const_y=(randv*(yoffset[1]-yoffset[0])+yoffset[0])
        coordinates=[]
        for dat in self.kdTree.data:
            #do translation
            new_x=dat[0]+ const_x
            if new_x>x_max:
                new_x=-x_max+(new_x-x_max)
            new_y=dat[1]+ const_y
            if new_y>y_max:
                new_y=-y_max+(new_y-y_max)
            #perform rotation
            new_coords_clockwise_rotation=[(-1)*(new_x),(-1)*(new_y)]
            coordinates.append([new_coords_clockwise_rotation[0],new_coords_clockwise_rotation[1]])
        return np.asarray(coordinates)
    #do the transformation and return geographic coordinates for display 
    @pyqtSlot(result=str)
    def getTransformedCoordinates(self):
        randv=random.random()
        self.random=randv
        metercoords=self.transformCoordinates(self.random)
        print ('The key for transformation was '+str(self.random))
        geographiccoords=[]
        for coords in metercoords:
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(coords[0],coords[1])
            point.Transform(transf3857to4326)
            geographiccoords.append([point.GetX(),point.GetY()])
        return json.dumps(geographiccoords)
    
    @pyqtSlot(str,result=str)
    def checkKeyExists(self,key):
        cnt= Keys.select().where(Keys.name==key).count()
        if (cnt==0):
            return 'n'
        return 'y'

    @pyqtSlot(str,str)
    def AddKey(self,key,value,transbounds):
        newd={}
        newd['name']=key
        newd['keyval']=value
        newd['created_at']=datetime.datetime.now()
        newd['transbounds']=transbounds
        k=Keys()
        k.create(**newd)

    @pyqtSlot(result=str)
    def getAllKeys(self):
        q=Keys.select(Keys.name).order_by(Keys.created_at.asc()).alias('name')
        out=[]
        for k in q:
            out.append(k.name)
        return json.dumps(out)
        
    #download the transformed coordinates
    @pyqtSlot(str,str,result=str)
    def downloadTransformed(self,newfname,key):
        randomvalue=None
        if (self.checkKeyExists(key)=='y'):
            return "Duplicate Key"
        randomvalue=self.random
        metercoords=self.transformCoordinates(randomvalue)
        transbounds=str(np.min(metercoords[:,0]))+","+str(np.min(metercoords[:,1]))+","+str(np.max(metercoords[:,0]))+","+str(np.max(metercoords[:,1]))
        self.AddKey(key,self.random,transbounds)
        randomvalue=self.random
        with fiona.open(self.currFile) as src:
            schema=src.schema
            outdir=self.outputfolder
            with fiona.open(outdir+'\\'+newfname+'.shp','w',crs=from_epsg(3857),schema=schema,driver=src.driver) as sink:
                for i in range(len(src)):
                    dat=metercoords[i]
                    elem=copy.deepcopy(src[i])
                    elem['geometry']['coordinates']=(dat[0],dat[1])
                    sink.write(elem)
        return "File downloaded successfully"

    #set the output folder
    @pyqtSlot(result=str)
    def setOutputFolder(self):
        folderName = str(QFileDialog.getExistingDirectory(self, "Select Directory"))
        if( not folderName):
            folderName=""
        self.outputfolder=folderName
        return folderName

    @pyqtSlot(result=str)
    def isOutputFolderSet(self):
        res="N"
        if self.outputfolder is not None:
            res="Y"
        return res

def main():
    app = QApplication(sys.argv)
    form = Explorer()
    form.show()
    app.exec_()

if __name__ == '__main__':              # if we're running file directly and not importing it
    gdal.PushErrorHandler(gdal_error_handler)
    main()                              # run the main function


