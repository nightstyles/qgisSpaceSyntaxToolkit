# -*- coding: utf-8 -*-
"""
/***************************************************************************
 essTools
                                 A QGIS plugin
 Set of tools for space syntax network analysis and results exploration
                              -------------------
        begin                : 2014-04-01
        copyright            : (C) 2014 by Jorge Gil, UCL
        email                : jorge.gil@ucl.ac.uk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

"""
# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *

from ..utility_functions import *

import time

try:
    import igraph as ig
    has_igraph = True
except ImportError, e:
    has_igraph = False


class AxialVerification(QThread):
    verificationFinished = pyqtSignal(dict, list)
    verificationProgress = pyqtSignal(int)
    verificationError = pyqtSignal(str)

    def __init__( self, parentThread, parentObject, settings, axial, id, unlinks, links):
        QThread.__init__( self, parentThread)
        self.parent = parentObject
        self.running = False
        self.verification_settings = settings
        self.axial_layer = axial
        self.unlinks_layer = unlinks
        self.links_layer = links
        self.user_id = id

        # verification globals
        self.problem_nodes = []
        # error types to identify:
        self.axial_errors = {'orphan':[],'island':[],'short line':[],'invalid geometry':[],'polyline':[],\
                            'coinciding points':[],'small line':[],'duplicate geometry':[],'overlap':[]}
        self.connection = None

    def run(self):
        self.running = True
        # reset all the errors
        self.problem_nodes = []
        for k, v in self.axial_errors.iteritems():
            self.axial_errors[k]=[]
        provider = self.axial_layer.storageType()
        #caps = self.axial_layer.dataProvider().capabilities()
        graph_links = None
        if 'spatialite' in provider.lower():
            # get the relevant layers
            unlinkname = ''
            if self.unlinks_layer:
                unlinkname = getLayerTableName(self.unlinks_layer)
                if not testSameDatabase([self.unlinks_layer, self.axial_layer]):
                    self.verificationError.emit("The map layer must be in the same database as the unlinks layer.")
                    return
            linkname = ''
            if self.links_layer:
                linkname = getLayerTableName(self.links_layer)
                if not testSameDatabase([self.links_layer, self.axial_layer]):
                    self.verificationError.emit("The map layer must be in the same database as the links layer.")
                    return
            axialname = getLayerTableName(self.axial_layer)
            self.connection = getLayerConnection(self.axial_layer)
            # get the geometry column name and other properties
            start_time = time.time()
            geomname = self.spatialitePreparation(self.connection, axialname)
            print "Preparing the map: %s"%str(time.time()-start_time)
            self.verificationProgress.emit(5)
            # analyse the geometry
            start_time = time.time()
            self.spatialiteTestGeometry(self.connection, axialname, geomname)
            print "Analysing geometry: %s"%str(time.time()-start_time)
            self.verificationProgress.emit(80)
            # build the topology
            if has_igraph:
                start_time = time.time()
                graph_links = self.spatialiteBuildTopology(self.connection, axialname, geomname, unlinkname, linkname)
                print "Building topology: %s"%str(time.time()-start_time)
            self.verificationProgress.emit(90)
            self.connection.close()
        #elif 'postgresql' in provider.lower():
            # newfeature: implement for postgis specific functions
        else:
            # create spatial index
            start_time = time.time()
            index = createIndex(self.axial_layer)
            print "Creating spatial index: %s"%str(time.time()-start_time)
            self.verificationProgress.emit(5)
            # analyse the geometry and topology
            start_time = time.time()
            graph_links = self.qgisGeometryTopologyTest(self.axial_layer, index, self.unlinks_layer, self.links_layer)
            print "Analysing geometry and topology: %s"%str(time.time()-start_time)
        # analyse the topology with igraph
        if len(graph_links) > 0 and has_igraph:
            start_time = time.time()
            # get user ids
            if self.user_id == '':
                axialids = self.axial_layer.allFeatureIds()
            else:
                axialids = getFieldValues(self.axial_layer, self.user_id)
            # uses igraph to test islands. look for orphans with the geometry test
            self.igraphTestTopology(graph_links, axialids)
            print "Analysing topology: %s"%str(time.time()-start_time)
        self.verificationProgress.emit(100)
        # return the results
        self.problem_nodes = list(set(self.problem_nodes))
        self.verificationFinished.emit(self.axial_errors, self.problem_nodes)
        #self.verificationProgress.emit(0)
        return

    def stop(self):
        self.running = False
        self.exit()
        #self.quit()
        #self.terminate()


    def igraphTestTopology(self, graph_links, graph_nodes):
        # create an igraph graph object and store the axial links
        try:
            g = ig.Graph(graph_links)
        except:
            return False
        # ideally g would be created with a list of edges based on 0 indexed and continuous vertices
        # but sqlite rowid is 1 indexed and might have gaps as it is a unique and persistent numbering
        # igraph adds 0 and other missing vertices, these must be identified and removed
        to_delete = []
        for v in g.vs:
            if v.index not in graph_nodes:
                to_delete.append(v.index)
        g.delete_vertices(to_delete)
        # deleting 0 reassigns all the indices, and creates a new 0.
        # the vertex reference to use to identify features must be a fid attribute
        g.vs["fid"] = graph_nodes
        if not g.is_connected():
            start_time = time.time()
            components = g.components()
            if components.__len__ > 1:
                giant = components.giant().vcount()
                islands = []
                # get vertex ids
                for i, cluster in enumerate(components):
                    if len(cluster) == 1:
                        node = g.vs[cluster]['fid'][0]
                        if node not in self.axial_errors['orphan']:
                            self.axial_errors['orphan'].append(node)
                            self.problem_nodes.append(node)
                    elif len(cluster) > 1 and len(cluster) != giant:
                        nodes = g.vs[cluster]['fid']
                        islands.append(nodes)
                        self.problem_nodes.extend(nodes)
                # add results to the list of problems
                if islands:
                    self.axial_errors['island'] = islands
            print "analyse orphans/islands: %s"%str(time.time()-start_time)
        return True


    # spatialite based functions
    #
    def spatialitePreparation(self, connection, axialname):
        query = """SELECT f_geometry_column, spatial_index_enabled FROM geometry_columns WHERE f_table_name = '%s'"""%(axialname)
        header, data, error = executeSpatialiteQuery(connection, query)
        geomname = data[0][0]
        # ensure that it has a spatial index
        if data[0][1] == 0:
            query = """SELECT CreateSpatialIndex('%s', '%s')"""%(axialname,geomname)
            header, data, error = executeSpatialiteQuery(connection, query, True)
        return geomname

    def spatialiteTestGeometry(self, connection, axialname, geomname):
        # this function checks the geometric validity of geometry using spatialite
        length = self.verification_settings['ax_min']
        threshold = self.verification_settings['ax_dist']
        if self.user_id == '':
            idcol = 'ROWID'
        else:
            idcol = self.user_id
        # geometry is valid (generally)
        start_time = time.time()
        query = """SELECT "%s" FROM %s WHERE NOT ST_IsSimple(%s) OR NOT ST_IsValid(%s)"""%(idcol, axialname, geomname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['invalid geometry'] = nodes
        self.verificationProgress.emit(10)
        print "analyse valid: %s"%str(time.time()-start_time)
        # geometry is polyline
        start_time = time.time()
        query = """SELECT "%s" FROM %s WHERE ST_NPoints(%s) <> 2 """%(idcol, axialname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['polyline'] = nodes
        self.verificationProgress.emit(15)
        print "analyse polyline: %s"%str(time.time()-start_time)
        # has two coinciding points
        start_time = time.time()
        query = """SELECT "%s" FROM %s WHERE ST_Equals(ST_StartPoint(%s),ST_EndPoint(%s))"""%(idcol, axialname, geomname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['coinciding points'] = nodes
        self.verificationProgress.emit(20)
        print "analyse coinciding: %s"%str(time.time()-start_time)
        # small lines, with small length
        start_time = time.time()
        query = """SELECT "%s" FROM %s WHERE ST_Length(%s)<%s"""%(idcol, axialname, geomname,length)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['small line'] = nodes
        self.verificationProgress.emit(25)
        print "analyse small: %s"%str(time.time()-start_time)
        # short lines, just about touch without intersecting
        start_time = time.time()
        query = 'SELECT a."%s" FROM %s a, %s b WHERE a."%s" <> b."%s" AND NOT ST_Intersects(a.%s,b.%s) AND'\
                '(PtDistWithin(ST_StartPoint(a.%s),b.%s,%s) OR PtDistWithin(ST_EndPoint(a.%s),b.%s,%s))'\
                'AND a.ROWID IN (SELECT ROWID FROM SpatialIndex WHERE f_table_name="%s" AND search_frame=b.%s)'\
                %(idcol, axialname, axialname, idcol, idcol, geomname, geomname, geomname, geomname, threshold,
                  geomname, geomname, threshold, axialname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['short line'] = nodes
        self.verificationProgress.emit(35)
        print "analyse short: %s"%str(time.time()-start_time)
        # duplicate geometry
        start_time = time.time()
        query = 'SELECT a."%s" FROM %s a, %s b WHERE a."%s" <> b."%s" AND ST_Equals(a.%s,b.%s)'\
                'AND a.ROWID IN (SELECT ROWID FROM SpatialIndex WHERE f_table_name="%s" AND search_frame=b.%s)'\
                %(idcol, axialname, axialname, idcol, idcol, geomname, geomname, axialname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['duplicate geometry'] = nodes
        self.verificationProgress.emit(40)
        print "analyse duplicate: %s"%str(time.time()-start_time)
        # geometry overlaps
        start_time = time.time()
        query = 'SELECT a."%s" FROM %s a, %s b WHERE a."%s" <> b."%s" AND NOT ST_Equals(a.%s,b.%s) AND ST_Overlaps(a.%s,b.%s)'\
            'AND a.ROWID IN (SELECT ROWID FROM SpatialIndex WHERE f_table_name="%s" AND search_frame=b.%s)'\
            %(idcol, axialname, axialname, idcol, idcol, geomname, geomname, geomname, geomname, axialname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['overlap'] = nodes
        self.verificationProgress.emit(60)
        print "analyse overlap: %s"%str(time.time()-start_time)
        # the overlap function alone might be too accurate for a GIS
        # an alternative function with buffer is too slow
        # test for orphans
        start_time = time.time()
        query = 'SELECT "%s" FROM %s WHERE "%s" NOT IN (SELECT DISTINCT(a."%s") FROM %s a, %s b ' \
            'WHERE a."%s" <> b."%s" AND ST_Intersects(a.%s,b.%s) '\
            'AND a.ROWID IN (SELECT ROWID FROM SpatialIndex WHERE f_table_name="%s" AND search_frame=b.%s))'\
            %(idcol, axialname, idcol, idcol, axialname, axialname, idcol, idcol, geomname, geomname, axialname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query)
        if data:
            nodes = list(zip(*data)[0])
            self.problem_nodes.extend(nodes)
            self.axial_errors['orphan'] = nodes
        print "analyse orphans: %s"%str(time.time()-start_time)
        self.verificationProgress.emit(80)

    def spatialiteBuildTopology(self, connection, axialname, geomname, unlinkname, linkname):
        # this function builds the axial map topology using spatialite. it's much faster.
        if self.user_id == '':
            idcol = 'ROWID'
        else:
            idcol = self.user_id
        # remove temporary table if already exists
        graphname = "temp_axial_topology"
        header, data, error = executeSpatialiteQuery(connection,"""DROP TABLE IF EXISTS "%s" """ % graphname)
        start_time = time.time()
        # create a new temporary table
        query = """CREATE TEMP TABLE %s (pk_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, a_fid INTEGER, b_fid INTEGER)"""%(graphname)
        header, data, error = executeSpatialiteQuery(connection, query)
        # calculate edges from intersecting feature pairs
        query = 'INSERT INTO %s (a_fid, b_fid) SELECT DISTINCT CASE WHEN a."%s" < b."%s" THEN a."%s" ELSE b."%s" END AS least_col, '\
                'CASE WHEN a."%s" > b."%s" THEN a."%s" ELSE b."%s" END AS greatest_col '\
                'FROM %s a, %s b WHERE a."%s" <> b."%s" AND Intersects(a.%s,b.%s) '\
                'AND a.ROWID IN (SELECT ROWID FROM SpatialIndex WHERE f_table_name="%s" AND search_frame=b.%s)'\
                %(graphname, idcol, idcol, idcol, idcol, idcol, idcol, idcol, idcol, axialname, axialname, idcol, idcol,
                  geomname, geomname, axialname, geomname)
        header, data, error = executeSpatialiteQuery(connection, query, commit=True)
        print "Building the graph: %s"%str(time.time()-start_time)
        # eliminate unlinks
        if unlinkname:
            if fieldExists(getLayerByName(unlinkname),'line1') and fieldExists(getLayerByName(unlinkname),'line2'):
                start_time = time.time()
                query = 'DELETE FROM %s WHERE cast(a_fid as text)||"_"||cast(b_fid as text) in (SELECT cast(line1 as text)||"_"||cast(line2 as text) FROM %s)'\
                        'OR cast(b_fid as text)||"_"||cast(a_fid as text) in (SELECT cast(line1 as text)||"_"||cast(line2 as text) FROM %s)'\
                        %(graphname, unlinkname, unlinkname)
                header, data, error = executeSpatialiteQuery(connection, query, commit=True)
                print "Unlinking the graph: %s"%str(time.time()-start_time)
        # newfeature: implement inserting links
        # return all the links to build the graph
        query = """SELECT a_fid, b_fid FROM %s"""%(graphname)
        header, data, error = executeSpatialiteQuery(connection, query)
        return data


    # QGIS based functions
    #
    def qgisGeometryTopologyTest(self, axial, index, unlinks, links):
        # this function checks the geometric validity of geometry using QGIS
        length = self.verification_settings['ax_min']
        threshold = self.verification_settings['ax_dist']
        axial_links = []
        unlinks_list = []
        links_list = []
        # get unlinks pairs
        if unlinks:
            if fieldExists(unlinks,'line1') and fieldExists(unlinks,'line2'):
                features = unlinks.getFeatures(QgsFeatureRequest().setSubsetOfAttributes(['line1','line2'],unlinks.pendingFields()))
                for feature in features:
                    unlinks_list.append((feature.attribute('line1'),feature.attribute('line2')))
        # get links pairs
        if links:
            features = links.getFeatures(QgsFeatureRequest().setSubsetOfAttributes(['line1','line2'],links.pendingFields()))
            for feature in features:
                links_list.append((feature.attribute('line1'),feature.attribute('line2')))
        if self.user_id == '':
            features = axial.getFeatures(QgsFeatureRequest().setSubsetOfAttributes([]))
        else:
            field = getFieldIndex(axial, self.user_id)
            features = axial.getFeatures(QgsFeatureRequest().setSubsetOfAttributes([field]))
        steps = 85.0/float(axial.featureCount())
        progress = 5.0
        start_buff = QgsGeometry()
        end_buff = QgsGeometry()
        for i, feature in enumerate(features):
            #row = i+1
            has_problem = False
            geom = feature.geometry()
            if self.user_id == '':
                id = feature.id()
            else:
                id = feature.attribute(self.user_id)
            # geometry is valid (generally)
            if not geom.isGeosValid() or geom.isGeosEmpty():
                has_problem = True
                self.axial_errors['invalid geometry'].append(id)
            # geometry is polyline
            if len(geom.asPolyline()) > 2:
                has_problem = True
                self.axial_errors['polyline'].append(id)
            # has two coinciding points
            if geom.length() == 0:
                has_problem = True
                self.axial_errors['coinciding points'].append(id)
            # small lines, with small length
            if geom.length() < length:
                has_problem = True
                self.axial_errors['small line'].append(id)
            # testing against other lines in the layer
            buff = None
            if threshold > 0:
                start_buff = QgsGeometry.fromPoint(geom.asPolyline()[0]).buffer(threshold,4)
                end_buff = QgsGeometry.fromPoint(geom.asPolyline()[1]).buffer(threshold,4)
                buff = geom.buffer(threshold,4)
                box = buff.boundingBox()
            else:
                box = geom.boundingBox()
            request = QgsFeatureRequest()
            if index:
                # should be faster to retrieve from index (if available)
                ints = index.intersects(box)
                request.setFilterFids(ints)
            else:
                # can retrieve objects using bounding box
                request.setFilterRect(box)
            if self.user_id == '':
                request.setSubsetOfAttributes([])
            else:
                field = getFieldIndex(axial, self.user_id)
                request.setSubsetOfAttributes([field])
            targets = axial.getFeatures(request)
            orphan = True
            for target in targets:
                geom_b = target.geometry()
                if self.user_id == '':
                    id_b = target.id()
                else:
                    id_b = target.attribute(self.user_id)
                if not id_b == id:
                    # duplicate geometry
                    if geom.isGeosEqual(geom_b):
                        has_problem = True
                        self.axial_errors['duplicate geometry'].append(id)
                    # geometry overlaps
                    if geom.overlaps(geom_b):
                        has_problem = True
                        self.axial_errors['overlap'].append(id)
                    # short lines, just about touch without intersecting
                    if (geom_b.intersects(start_buff) or geom_b.intersects(end_buff)) and not geom_b.intersects(geom):
                        has_problem = True
                        self.axial_errors['short line'].append(id)
                    if geom.intersects(geom_b):
                        # check if in the unlinks
                        if (id,id_b) not in unlinks_list and (id_b,id) not in unlinks_list:
                            # build the topology
                            if has_igraph:
                                #axial_links.append((convertNumeric(id),convertNumeric(id_b)))
                                axial_links.append((id,id_b))
                            # test orphans
                            if orphan:
                                orphan = False
            if orphan:
                has_problem = True
                self.axial_errors['orphan'].append(id)
            if has_problem:
                self.problem_nodes.append(id)
            progress += steps
            self.verificationProgress.emit(int(progress))
        return axial_links

    # PostGIS based functions
    #
    def postgisTestGeometry(self):
        # newfeature: support postgis axial verification
        pass

    def postgisBuildTopology(self):
        pass
