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

# Import required modules
from ExplorerDialog import ExplorerDialog
from AttributeSymbology import *
from AttributeStats import *
from AttributeCharts import *
from ..utility_functions import *

import numpy as np


class ExplorerTool(QObject):

    def __init__(self, iface, settings, project):
        QObject.__init__(self)

        self.iface = iface
        self.settings = settings
        self.project = project
        self.legend = self.iface.legendInterface()

        # initialise UI
        self.dlg = ExplorerDialog(self.iface.mainWindow())

        # set up GUI signals
        self.dlg.layerChanged.connect(self.updateLayerAttributes)
        self.dlg.symbologyApplyButton.clicked.connect(self.applySymbology)
        self.dlg.attributesList.currentRowChanged.connect(self.updateSymbology)
        self.dlg.attributesList.currentRowChanged.connect(self.updateStats)
        self.dlg.attributesList.currentRowChanged.connect(self.updateCharts)
        self.dlg.chartChanged.connect(self.updateCharts)
        self.dlg.dependentChanged.connect(self.updateCharts)
        self.dlg.explorerTabs.currentChanged.connect(self.updateActionConnections)
        self.dlg.dialogClosed.connect(self.onHide)
        self.dlg.visibilityChanged.connect(self.onShow)

        # connect signal/slots with main program
        self.legend.itemAdded.connect(self.updateLayers)
        self.legend.itemRemoved.connect(self.updateLayers)
        self.iface.projectRead.connect(self.updateLayers)
        self.iface.newProjectCreated.connect(self.updateLayers)

        # initialise attribute explorer classes
        self.attributeSymbology = AttributeSymbology(self.iface)
        self.attributeCharts = AttributeCharts(self.iface, self.dlg.chartPlotWidget)

        # initialise internal globals
        self.current_layer = None
        self.current_renderer = None
        self.attribute_statistics = []
        self.bivariate_statistics = []
        self.attribute_values = []
        self.selection_values = []
        self.selection_ids = []
        self.layer_ids = dict()
        self.updateActionConnections(0)
        self.isVisible = False


    def unload(self):
        if self.isVisible:
            # Disconnect signals from main program
            #self.legend.currentLayerChanged.disconnect(self.updateLayerAttributes)
            self.legend.itemAdded.disconnect(self.updateLayers)
            self.legend.itemRemoved.disconnect(self.updateLayers)
            self.iface.projectRead.disconnect(self.updateLayers)
            self.iface.newProjectCreated.disconnect(self.updateLayers)
            # clear stored values
            self.attribute_statistics = []
            self.bivariate_statistics = []
            self.attribute_values = []
            self.selection_values = []
            self.layer_ids = dict()
        self.isVisible = False

    def onShow(self):
        if self.dlg.isVisible():
            # Connect signals to QGIS interface
            #self.legend.currentLayerChanged.connect(self.updateLayerAttributes)
            self.legend.itemAdded.connect(self.updateLayers)
            self.legend.itemRemoved.connect(self.updateLayers)
            self.iface.projectRead.connect(self.updateLayers)
            self.iface.newProjectCreated.connect(self.updateLayers)
            self.updateLayers()
            self.isVisible = True

    def onHide(self):
        if self.isVisible:
            # Disconnect signals to QGIS interface
            #self.legend.currentLayerChanged.disconnect(self.updateLayerAttributes)
            self.legend.itemAdded.disconnect(self.updateLayers)
            self.legend.itemRemoved.disconnect(self.updateLayers)
            self.iface.projectRead.disconnect(self.updateLayers)
            self.iface.newProjectCreated.disconnect(self.updateLayers)
            # clear stored values
            self.attribute_statistics = []
            self.bivariate_statistics = []
            self.attribute_values = []
            self.selection_values = []
            self.layer_ids = dict()
        self.isVisible = False

    ##
    ## manage project and tool settings
    ##
    def getProjectSettings(self):
        # pull relevant settings from project manager
        for i, attr in enumerate(self.layer_attributes):
            settings = self.project.getGroupSettings("symbology/"+self.current_layer.name()+"/"+attr["name"])
            if settings:
                #newfeature: allow custom symbology in the layer to be explored
                # feature almost in place, but all implications are not fully understood yet
                #if self.current_layer.rendererV2().usedAttributes() == attr["name"]:
                #    self.current_renderer = self.current_layer.rendererV2()
                #    self.layer_display_settings[i]["colour_range"] = 4
                #else:
                #    self.current_renderer = None
                self.layer_display_settings[i] = settings
        #self.project.readSettings(self.axial_analysis_settings,"stats")

    def updateProjectSettings(self, attr):
        # store last used setting with project
        symbology = self.layer_display_settings[attr]
        self.project.writeSettings(symbology,"symbology/"+self.current_layer.name()+"/"+symbology["attribute"])
        #self.project.writeSettings(self.axial_analysis_settings,"stats")

    def getToolkitSettings(self):
        # pull relevant settings from settings manager: self.settings
        # newfeature: get relevant settings from tool
        pass

    def updateToolkitSettings(self):
        # newfeature: save layer edit settings to toolkit
        pass

    ##
    ## Manage layers and attributes
    ##
    def updateLayers(self):
        try:
            # fixme: throws NoneType error occasionally when adding/removing layers. trapping it for now.
            layers = getLegendLayers(self.iface)
        except:
            layers = []
        is_numeric = []
        idx = 0
        if len(layers) > 0:
            for layer in layers:
                if layer.type() == 0:  #VectorLayer
                    fields = getNumericFields(layer)
                    if len(fields) > 0:
                        is_numeric.append(layer.name())
                        if self.current_layer and layer.name() == self.current_layer.name():
                            idx = len(is_numeric)
                            if not self.legend.isLayerVisible(layer):
                                self.legend.setLayerVisible(layer, True)
                                self.legend.setCurrentLayer(layer)
        if len(is_numeric) == 0:
            is_numeric.append("Open a vector layer with numeric fields")
        else:
            is_numeric.insert(0,"Select layer to explore...")
        self.dlg.setCurrentLayer(is_numeric,idx)

    def updateLayerAttributes(self):
        # get selected layer
        layer = self.dlg.getCurrentLayer()
        no_layer = False
        try:
            # fixme: throws NoneType error occasionally when removing layers. trapping it for now.
            self.current_layer = getLegendLayerByName(self.iface, layer)
        except:
            self.current_layer = None
        # get layer attributes
        if self.current_layer is not None:
            if not self.legend.isLayerVisible(self.current_layer):
                self.legend.setLayerVisible(self.current_layer, True)
            if self.current_layer.type() == 0:  #VectorLayer
                try:
                    # fixme: throws NoneType error occasionally when removing layers. trapping it for now.
                    #field_names = getNumericFieldNames(self.current_layer)
                    numeric_field_ids, numeric_fields = getValidFields(self.current_layer,type=(QVariant.Int, QVariant.LongLong, QVariant.Double, QVariant.UInt, QVariant.ULongLong),null="all")
                except:
                    numeric_fields = []
                    numeric_field_ids = []
                if len(numeric_fields) > 0:
                    # set min and max values of attributes
                    # set this layer's default display attributes
                    self.layer_display_settings = []
                    self.layer_attributes = []
                    for i, index in enumerate(numeric_field_ids):
                        max_value = self.current_layer.maximumValue(index)
                        min_value = self.current_layer.minimumValue(index)
                        # set the layer's attribute info
                        attribute_info = dict()
                        attribute_info["id"]=index
                        attribute_info["name"]=numeric_fields[i]
                        attribute_info["min"]=min_value
                        attribute_info["max"]=max_value
                        self.layer_attributes.append(attribute_info)
                        # set default display settings
                        attribute_display = dict(attribute="", colour_range=0, line_width=0.25, invert_colour=0, display_order=0,
                        intervals=10, interval_type=0, top_percent=100, top_value=0.0, bottom_percent=0, bottom_value=0.0)
                        # update the top and bottom value of the defaults
                        attribute_display["attribute"] = numeric_fields[i]
                        attribute_display["top_value"] = float(max_value)
                        attribute_display["bottom_value"] = float(min_value)
                        self.layer_display_settings.append(attribute_display)
                    # get the current display attribute
                    attributes = self.current_layer.rendererV2().usedAttributes()
                    if len(attributes) > 0:
                        display_attribute = attributes[0]
                        if display_attribute in numeric_fields:
                            current_attribute = numeric_fields.index(display_attribute)
                        else:
                            current_attribute = 0
                    else:
                        current_attribute = -1
                    # check for saved display settings for the given layer
                    self.getProjectSettings()
                    # update the dialog with this info
                    self.dlg.setAttributesList(self.layer_attributes)
                    self.dlg.setAttributesSymbology(self.layer_display_settings)
                    self.dlg.setCurrentAttribute(current_attribute)
                    self.dlg.lockTabs(False)
                    #
                    self.updateSymbology()
                else:
                    no_layer = True
            else:
                no_layer = True
        else:
            no_layer = True
        if no_layer:
            self.current_layer = None #QgsVectorLayer()
            self.dlg.setAttributesList([])
            self.dlg.setAttributesSymbology([])
            self.dlg.setCurrentAttribute(-1)
            self.dlg.lockTabs(True)


    def updateActionConnections(self, tab):
        # change signal connections to trigger actions depending on selected tab
        # disconnect stats and charts
        if tab == 0:
            try:
                self.dlg.attributesList.currentRowChanged.disconnect(self.updateStats)
                self.iface.mapCanvas().selectionChanged.disconnect(self.updateStats)
            except Exception: pass
            try:
                self.dlg.attributesList.currentRowChanged.disconnect(self.updateCharts)
                self.iface.mapCanvas().selectionChanged.disconnect(self.updateCharts)
            except Exception: pass
        # do not disconnect symbology as it just retrieves info and updates the display: required
        # connect calculate stats
        elif tab == 1:
            try:
                self.dlg.attributesList.currentRowChanged.connect(self.updateStats)
                self.iface.mapCanvas().selectionChanged.connect(self.updateStats)
            except Exception: pass
            try:
                self.dlg.attributesList.currentRowChanged.disconnect(self.updateCharts)
                self.iface.mapCanvas().selectionChanged.disconnect(self.updateCharts)
            except Exception: pass
            self.updateStats()
        # connect calculate charts
        elif tab == 2:
            try:
                self.dlg.attributesList.currentRowChanged.disconnect(self.updateStats)
                self.iface.mapCanvas().selectionChanged.disconnect(self.updateStats)
            except Exception: pass
            try:
                self.dlg.attributesList.currentRowChanged.connect(self.updateCharts)
                self.iface.mapCanvas().selectionChanged.connect(self.updateCharts)
            except Exception: pass
            self.updateCharts()


    ##
    ## Symbology actions
    ##
    def applySymbology(self):
        """
        Update the current layer's display settings dictionary.
        Then update the layer display settings in the dialog.
        Finally, update the display using the new settings.
        """
        current_attribute = self.dlg.getCurrentAttribute()
        self.layer_display_settings[current_attribute] = self.dlg.getUpdatedDisplaySettings()
        self.updateProjectSettings(current_attribute)
        self.dlg.setAttributesSymbology(self.layer_display_settings)
        self.updateSymbology()

    def updateSymbology(self):
        """
        Identifies the current attribute, gets its current display settings

        @param idx: the id of the selected attribute in the dialog's attributes list
        """
        if self.current_layer is not None:
            current_attribute = self.dlg.getCurrentAttribute()
            attribute = self.layer_attributes[current_attribute]
            # make this the tooltip attribute
            self.current_layer.setDisplayField(attribute["name"])
            if not self.iface.actionMapTips().isChecked():
                self.iface.actionMapTips().trigger()
            # get display settings
            settings = self.layer_display_settings[current_attribute]
            # produce new symbology renderer
            renderer = self.attributeSymbology.updateRenderer(self.current_layer, attribute, settings)
            # update the canvas
            if renderer:
                self.current_layer.setRendererV2(renderer)
                self.current_layer.triggerRepaint()
                self.iface.mapCanvas().refresh()
                self.legend.refreshLayerSymbology(self.current_layer)


    ##
    ## Stats actions
    ##
    def updateStats(self):
        if self.current_layer is not None:
            current_attribute = self.dlg.getCurrentAttribute()
            if current_attribute >= 0:
                attribute = self.layer_attributes[current_attribute]
                # check if stats have been calculated before
                idx = self.checkValuesAvailable(attribute)
                if idx == -1:
                    self.retrieveAttributeValues(attribute)
                    idx = len(self.attribute_statistics)-1
                stats = self.attribute_statistics[idx]
                # calculate stats of selected objects
                select_stats = None
                if self.current_layer.selectedFeatureCount() > 0:
                    select_stats = dict()
                    self.selection_values, self.selection_ids = getSelectionValues(self.current_layer, attribute["name"], null=False, id=True)
                    select_stats["Mean"] = np.nanmean(self.selection_values)
                    select_stats["Std Dev"] = np.nanstd(self.selection_values)
                    select_stats["Median"] = np.median(self.selection_values)
                    select_stats["Minimum"] = np.nanmin(self.selection_values)
                    select_stats["Maximum"] = np.nanmax(self.selection_values)
                    select_stats["Range"] = stats["Maximum"]-stats["Minimum"]
                    select_stats["1st Quart"] = np.percentile(self.selection_values,25)
                    select_stats["3rd Quart"] = np.percentile(self.selection_values,75)
                    select_stats["IQR"] = select_stats["3rd Quart"]-select_stats["1st Quart"]
                    select_stats["Gini"] = calcGini(self.selection_values)
                else:
                    self.selection_values = []
                    self.selection_ids = []
                # update the dialog
                self.dlg.setStats(stats, select_stats)
            #else:
            #    self.dlg.__clearStats()
        #else:
        #    self.dlg.__clearStats()

    ##
    ## Charts actions
    ##
    def updateCharts(self):
        if self.current_layer is not None:
            current_attribute = self.dlg.getCurrentAttribute()
            if current_attribute >= 0:
                attribute = self.layer_attributes[current_attribute]
                # check if values are already available
                idx = self.checkValuesAvailable(attribute)
                # retrieve attribute values
                if idx == -1:
                    self.retrieveAttributeValues(attribute)
                    idx = len(self.attribute_values)-1
                values = self.attribute_values[idx]["values"]
                ids = self.layer_ids[self.current_layer.name()]
                # retrieve selection values
                if self.current_layer.selectedFeatureCount() > 0:
                    self.selection_values, self.selection_ids = getSelectionValues(self.current_layer, attribute["name"], null=False, id=True)
                else:
                    self.selection_values = []
                    self.selection_ids = []
                # plot charts and dependent variable stats
                chart_type = self.dlg.getChartType()
                if chart_type == 0:
                    # filter out NULL values
                    nan_values = filter(None,values)
                    # newfeature: getting unique can be slow in large tables. thread?
                    #bins = getUniqueValuesNumber(self.current_layer, attribute["name"])
                    bins = 50
                    if bins > 0:
                        self.attributeCharts.drawHistogram(nan_values, attribute["min"], attribute["max"], bins)
                    # plot chart of selected objects
                    if len(self.selection_values) > 0:
                        nan_values = filter(None,self.selection_values)
                        self.attributeCharts.setHistogramSelection(nan_values, np.min(nan_values), np.max(nan_values), bins)
                # newfeature: implement box plot
                elif chart_type == 1:
                    self.attributeCharts.drawBoxPlot(values)
                elif chart_type == 2:
                    # calculate bi-variate stats
                    current_dependent = self.dlg.getYAxisAttribute()
                    if current_dependent != current_attribute:
                        dependent = self.layer_attributes[current_dependent]
                        idx = self.checkValuesAvailable(dependent)
                        if idx == -1:
                            self.retrieveAttributeValues(dependent)
                            idx = len(self.attribute_values)-1
                        yvalues = self.attribute_values[idx]["values"]
                        # check if it exists
                        idx = -1
                        for i, bistats in enumerate(self.bivariate_statistics):
                            if bistats["Layer"] == self.current_layer.name() and bistats["x"] == current_attribute and bistats["y"] == current_dependent:
                                idx = i
                                break
                        if idx == -1:
                            #calculate
                            bistats = dict()
                            bistats["Layer"] = self.current_layer.name()
                            bistats["x"] = current_attribute
                            bistats["y"] = current_dependent
                            bistats["r"] = round((np.corrcoef(values,yvalues)[1][0]),5)
                            bistats["r2"] = round((bistats["r"]*bistats["r"]),5)
                            bistats["p"] = 0 #round(calcPvalue(values,yvalues),5) fixme: pvalue calc not correct
                            # newfeature: calculate linear regression
                            bistats["line"] = ""
                            self.bivariate_statistics.append(bistats)
                        else:
                            bistats = self.bivariate_statistics[idx]
                        # update the dialog
                        self.dlg.setCorrelation(bistats)
                        # plot chart
                        # fixme: retrieve feature symbols from layer
                        #symbols = getAllFeatureSymbols(self.current_layer)
                        symbols = [QColor(200,200,200,255)] * len(ids)
                        self.attributeCharts.drawScatterplot(values, yvalues, ids, symbols)
                        # plot chart of selected objects
                        if len(self.selection_values) > 0:
                            all_ids = self.layer_ids[self.current_layer.name()]
                            indices = []
                            for id in self.selection_ids:
                                if id in all_ids:
                                    indices.append(all_ids.index(id))
                            self.attributeCharts.setScatterplotSelection(indices)
                    else:
                        self.dlg.clearDependentValues()
            else:
                self.dlg.clearDependentValues()
        else:
            self.dlg.clearDependentValues()

    def checkValuesAvailable(self, attribute):
        idx = -1
        for i, vals in enumerate(self.attribute_values):
            if vals["Layer"] == self.current_layer.name() and vals["Attribute"] == attribute["name"]:
                idx = i
                break
        return idx


    def retrieveAttributeValues(self, attribute):
        if self.layer_ids.has_key(self.current_layer.name()):
            values = getFieldValues(self.current_layer, attribute["name"], null=True, id=False)
        else:
            values, ids = getFieldValues(self.current_layer, attribute["name"], null=True, id=True)
            # store retrieved ids for charts
            self.layer_ids[self.current_layer.name()] = ids
        nan_values = filter(None,values)
        # calculate the stats
        stats = dict()
        stats["Layer"] = self.current_layer.name()
        stats["Attribute"] = attribute["name"]
        stats["Mean"] = np.nanmean(nan_values)
        stats["Std Dev"] = np.nanstd(nan_values)
        stats["Median"] = np.median(nan_values)
        stats["Minimum"] = np.nanmin(nan_values)
        stats["Maximum"] = np.nanmax(nan_values)
        stats["Range"] = stats["Maximum"]-stats["Minimum"]
        stats["1st Quart"] = np.percentile(nan_values,25)
        stats["3rd Quart"] = np.percentile(nan_values,75)
        stats["IQR"] = stats["3rd Quart"]-stats["1st Quart"]
        stats["Gini"] = calcGini(nan_values)
        # store the results
        self.attribute_statistics.append(stats)
        # store retrieved values for charts
        attr = dict()
        attr["Layer"] = self.current_layer.name()
        attr["Attribute"] = attribute["name"]
        attr["values"] = values
        self.attribute_values.append(attr)