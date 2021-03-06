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

from PyQt4 import QtCore, QtGui
from ui_Explorer import Ui_ExplorerDialog

from ..utility_functions import *


# try to use pyqtgraph, if not available use basic graph widget
try:
    import pyqtgraph as pg
    has_pyqtgraph = True
except ImportError, e:
    has_pyqtgraph = False

class ExplorerDialog(QtGui.QDockWidget, Ui_ExplorerDialog):
    dialogClosed = QtCore.pyqtSignal()
    layerChanged = QtCore.pyqtSignal()
    attributesLoaded = QtCore.pyqtSignal(int)
    dependentChanged = QtCore.pyqtSignal()
    chartChanged = QtCore.pyqtSignal()
    addSelection = QtCore.pyqtSignal(bool)

    def __init__(self, parent):
        QtGui.QDockWidget.__init__(self, parent)
        # Set up the user interface from Designer.
        self.setupUi(self)

        # Connect dialog's internal signals and slots
        #self.attributesLoaded.connect(self.__lockColourControls)
        self.layerCombo.currentIndexChanged.connect(self.__selectCurrentLayer)
        self.attributesList.currentRowChanged.connect(self.__lockApplyButton)
        self.attributesList.currentRowChanged.connect(self.__selectCurrentAttribute)
        # symbology colour range settings
        self.colourRangeCombo.currentIndexChanged.connect(self.__colourRangeSelected)
        self.lineWidthSpin.valueChanged.connect(self.__lineWidthChanged)
        self.invertColourCheck.stateChanged.connect(self.__invertColourChanged)
        self.displayOrderCombo.currentIndexChanged.connect(self.__displayOrderSelected)
        # symbology interval settings
        self.intervalSpin.valueChanged.connect(self.__intervalNumberChanged)
        self.intervalTypeCombo.activated.connect(self.__intervalTypeChanged)
        self.topLimitSpin.valueChanged.connect(self.__topLimitSpinClicked)
        self.topLimitText.editingFinished.connect(self.__topLimitTextChanged)
        self.bottomLimitSpin.valueChanged.connect(self.__bottomLimitSpinClicked)
        self.bottomLimitText.editingFinished.connect(self.__bottomLimitTextChanged)
        # charts
        self.histogramCheck.clicked.connect(self.__histogramSelected)
        self.boxplotCheck.clicked.connect(self.__boxplotSelected)
        self.scatterplotCheck.clicked.connect(self.__scatterplotSelected)
        self.yaxisCombo.currentIndexChanged.connect(self.yAxisChanged)

        # global variables
        self.layer_attributes = {}
        self.curr_attribute = 0
        self.attribute_min = 0.0
        self.attribute_max = 0.0
        self.symbology_settings = []
        self.chart_settings = []
        self.curr_chart = 0

        # default symbology values
        self.current_symbology = dict()
        self.current_symbology["colour_range"] = 0
        self.current_symbology["invert_colour"] = 0
        self.current_symbology["line_width"] = 0.25
        self.current_symbology["display_order"] = 0
        self.current_symbology["intervals"] = 10
        self.current_symbology["interval_type"] = 0
        self.current_symbology["top_percent"] = 100
        self.current_symbology["top_value"] = 0.0
        self.current_symbology["bottom_percent"] = 0
        self.current_symbology["bottom_value"] = 0.0

        # statistics labels
        self.__addStatsLabels()
        self.statisticsProgressBar.hide()

        # charts widgets
        self.lineLabel.hide()
        self.popoutButton.hide()
        self.boxplotCheck.hide()
        self.pLabel.hide()
        self.chartsProgressBar.hide()
        self.histogramCheck.setChecked(True)
        self.__lockDependentGroup(True)
        # add a pyqtgraph Plotwidget if the package is available, otherwise use a plain graphics view for painting on
        if has_pyqtgraph:
            self.chartPlotWidget = pg.PlotWidget(self.chartsTab)
            self.chartPlotWidget.enableAutoRange()
            # Enable/disable antialiasing for prettier plots, but much slower
            pg.setConfigOptions(antialias=False)
        else:
            self.chartPlotWidget = QtGui.QGraphicsView(self.chartsTab)
        self.chartPlotWidget.setFrameShape(QtGui.QFrame.NoFrame)
        self.chartPlotWidget.setFrameShadow(QtGui.QFrame.Sunken)
        self.chartPlotWidget.setObjectName("chartPlotWidget")
        self.chartsLayout.addWidget(self.chartPlotWidget)
        self.chartsLayout.setStretch(1, 2)


    #####
    # General functions of the explorer dialog
    def closeEvent(self, event):
        self.dialogClosed.emit()
        return QtGui.QDockWidget.closeEvent(self, event)

    def keyPressEvent(self, QKeyEvent):
        if QKeyEvent.key() == QtCore.Qt.Key_Shift:
            self.addSelection.emit(True)

    def keyReleaseEvent(self, QKeyEvent):
        if QKeyEvent.key() == QtCore.Qt.Key_Shift:
            self.addSelection.emit(False)


    # Layer and attributes group
    #
    def setCurrentLayer(self, names, idx=0):
        self.layerCombo.clear()
        self.layerCombo.addItems(names)
        if idx > 0:
            self.layerCombo.setCurrentIndex(idx)

    def __selectCurrentLayer(self):
        self.layerChanged.emit()

    def getCurrentLayer(self):
        return self.layerCombo.currentText()

    def setAttributesList(self, data):
        self.layer_attributes = data
        self.attributesList.clear()
        if len(data) > 0:
            # get the names for the list
            names = [attr["name"] for attr in self.layer_attributes]
            self.attributesList.addItems(names)
            self.__setYAxisCombo(names)
            self.__lockColourControls(False)
        else:
            self.__setYAxisCombo([])
            #self.clearPlot()
            self.__lockColourControls(True)
        #self.attributesLoaded.emit(self.attributesList.count())

    def setAttributesSymbology(self, data):
        self.symbology_settings = data

    def setCurrentAttribute(self, idx):
        self.attributesList.setCurrentRow(idx)
        # fixme: when changing layer, stats and chart update is not happening (though the function is called!)

    def getCurrentAttribute(self):
        return self.attributesList.currentRow()

    def __selectCurrentAttribute(self):
        self.curr_attribute = self.attributesList.currentRow()
        if self.curr_attribute >= 0:
            self.__loadDisplaySettings()

    def __loadDisplaySettings(self):
        attribute = self.layer_attributes[self.curr_attribute]
        self.attribute_max = attribute["max"]
        self.attribute_min = attribute["min"]
        # get current display settings
        settings = self.symbology_settings[self.curr_attribute]
        for key in settings.iterkeys():
            self.current_symbology[key] = settings[key]
        # update the interface
        self.setColourRanges(int(self.current_symbology["colour_range"]))
        self.setLineWidthSpin(float(self.current_symbology["line_width"]))
        self.setInvertColour(int(self.current_symbology["invert_colour"]))
        self.setDisplayOrder(int(self.current_symbology["display_order"]))
        self.setIntervalSpin(int(self.current_symbology["intervals"]))
        self.setIntervalType(int(self.current_symbology["interval_type"]))
        self.setTopLimitSpin(int(self.current_symbology["top_percent"]))
        self.setTopLimitText(str(self.current_symbology["top_value"]))
        self.setBottomLimitSpin(int(self.current_symbology["bottom_percent"]))
        self.setBottomLimitText(str(self.current_symbology["bottom_value"]))

    def getUpdatedDisplaySettings(self):
        settings = dict()
        for key in self.current_symbology.iterkeys():
            settings[key] = self.current_symbology[key]
        return settings

    def lockTabs(self, onoff):
        self.explorerTabs.setDisabled(onoff)
        self.__clearStats()
        self.clearPlot()

    # Symbology group
    #
    def __lockApplyButton(self, onoff):
        if not onoff and self.current_symbology["top_value"] is not None and self.current_symbology["bottom_value"] is not None:
            self.symbologyApplyButton.setDisabled(onoff)
        else:
            self.symbologyApplyButton.setDisabled(onoff)

    def __lockColourControls(self, onoff):
        #set all the colour and interval controls
        if self.attributesList.count() == 0 or self.current_symbology["colour_range"] != 4:
            self.colourRangeCombo.setDisabled(onoff)
        self.invertColourCheck.setDisabled(onoff)
        self.displayOrderCombo.setDisabled(onoff)
        self.lineWidthSpin.setDisabled(onoff)
        self.intervalSpin.setDisabled(onoff)
        self.intervalTypeCombo.setDisabled(onoff)
        if onoff == True or self.current_symbology["interval_type"] == 3:
            self.__lockCustomIntervalControls(onoff)
        self.__lockApplyButton(onoff)

    def __lockCustomIntervalControls(self, onoff):
        self.topLimitLabel.setDisabled(onoff)
        self.topLimitSpin.setDisabled(onoff)
        self.topLimitText.setDisabled(onoff)
        self.bottomLimitLabel.setDisabled(onoff)
        self.bottomLimitSpin.setDisabled(onoff)
        self.bottomLimitText.setDisabled(onoff)

    # Colour settings
    def setColourRanges(self, idx):
        self.colourRangeCombo.setCurrentIndex(idx)
        #self.__colourRangeSelected(idx)

    def __colourRangeSelected(self, idx):
        self.current_symbology["colour_range"] = idx
        if idx == 4:
            self.__lockColourControls(True)
        else:
            self.__lockColourControls(False)

    def setLineWidthSpin(self, value):
        self.lineWidthSpin.setValue(value)

    def __lineWidthChanged(self, value):
        self.current_symbology["line_width"] = value

    def setInvertColour(self, onoff):
        self.invertColourCheck.setChecked(onoff)

    def __invertColourChanged(self, onoff):
        if onoff:
            self.current_symbology["invert_colour"] = 1
        else:
            self.current_symbology["invert_colour"] = 0

    def setDisplayOrder(self, idx):
        self.displayOrderCombo.setCurrentIndex(idx)
        #self.__displayOrderSelected(idx)

    def __displayOrderSelected(self, idx):
        self.current_symbology["display_order"] = idx

    # Interval settings
    def setIntervalSpin(self, value):
        self.intervalSpin.setValue(value)

    def __intervalNumberChanged(self, value):
        self.current_symbology["intervals"] = value

    def setIntervalType(self, idx):
        self.intervalTypeCombo.setCurrentIndex(idx)
        self.__intervalTypeChanged(idx)

    def __intervalTypeChanged(self, idx):
        self.current_symbology["interval_type"] = idx
        if self.current_symbology["interval_type"] == 3:
            self.__lockCustomIntervalControls(False)
        else:
            self.__lockCustomIntervalControls(True)
            self.current_symbology["top_value"] = self.attribute_max
            self.current_symbology["bottom_value"] = self.attribute_min
            self.__lockApplyButton(False)

    def __topLimitSpinClicked(self, value):
        self.current_symbology["top_percent"] = value
        # calculate spin absolute value
        spin = str(((self.attribute_max-self.attribute_min)*self.current_symbology["top_percent"]/100)+self.attribute_min)
        self.setTopLimitText(spin)
        self.bottomLimitSpin.setMaximum(value)

    def setTopLimitText(self, txt):
        self.topLimitText.blockSignals(True)
        self.topLimitText.clear()
        self.topLimitText.setText(txt)
        self.current_symbology["top_value"] = float(txt)
        self.topLimitText.blockSignals(False)

    def __topLimitTextChanged(self):
        value = self.topLimitText.text()
        try:
            self.current_symbology["top_value"] = float(value)
            if self.current_symbology["top_value"] >= self.current_symbology["bottom_value"] and self.current_symbology["top_value"] <= self.attribute_max:
                # calculate spin percentage
                spin = abs(((self.current_symbology["top_value"]-self.attribute_min)/(self.attribute_max-self.attribute_min))*100)
                self.setTopLimitSpin(spin)
                self.bottomLimitSpin.setMaximum(spin)
                self.__lockApplyButton(False)
            else:
                self.current_symbology["top_value"] = None
                self.__lockApplyButton(True)
        except:
            self.current_symbology["top_value"] = None
            self.__lockApplyButton(True)

    def setTopLimitSpin(self, value):
        self.topLimitSpin.blockSignals(True)
        self.topLimitSpin.setValue(value)
        self.current_symbology["top_percent"] = value
        self.topLimitSpin.blockSignals(False)

    def __bottomLimitSpinClicked(self, value):
        self.current_symbology["bottom_percent"] = value
        # calculate spin absolute value
        spin = str(((self.attribute_max-self.attribute_min)*self.current_symbology["bottom_percent"]/100)+self.attribute_min)
        self.setBottomLimitText(spin)
        self.topLimitSpin.setMinimum(value)

    def setBottomLimitText(self, txt):
        self.bottomLimitText.blockSignals(True)
        self.bottomLimitText.clear()
        self.bottomLimitText.setText(txt)
        self.current_symbology["bottom_value"] = float(txt)
        self.bottomLimitText.blockSignals(False)

    def __bottomLimitTextChanged(self):
        value = self.bottomLimitText.text()
        try:
            self.current_symbology["bottom_value"] = float(value)
            if self.current_symbology["bottom_value"] <= self.current_symbology["top_value"] and self.current_symbology["bottom_value"] >= self.attribute_min:
                # calculate spin percentage
                spin = abs(((self.current_symbology["bottom_value"]-self.attribute_min)/(self.attribute_max-self.attribute_min))*100)
                self.setBottomLimitSpin(spin)
                self.topLimitSpin.setMinimum(spin)
                self.__lockApplyButton(False)
            else:
                self.current_symbology["bottom_value"] = None
                self.__lockApplyButton(True)
        except:
            self.current_symbology["bottom_value"] = None
            self.__lockApplyButton(True)

    def setBottomLimitSpin(self, value):
        self.bottomLimitSpin.blockSignals(True)
        self.bottomLimitSpin.setValue(value)
        self.current_symbology["bottom_percent"] = value
        self.bottomLimitSpin.blockSignals(False)

    #
    # Statistics group
    #
    def __addStatsLabels(self):
        self.statisticsTable.setHorizontalHeaderLabels(["Statistic","Value","Selection"])
        self.statisticsTable.setRowCount(10)
        self.statisticsTable.setItem(0,0,QTableWidgetItem("Mean"))
        self.statisticsTable.setItem(1,0,QTableWidgetItem("Std Dev"))
        self.statisticsTable.setItem(2,0,QTableWidgetItem("Median"))
        self.statisticsTable.setItem(3,0,QTableWidgetItem("Minimum"))
        self.statisticsTable.setItem(4,0,QTableWidgetItem("Maximum"))
        self.statisticsTable.setItem(5,0,QTableWidgetItem("Range"))
        self.statisticsTable.setItem(6,0,QTableWidgetItem("1st Quart"))
        self.statisticsTable.setItem(7,0,QTableWidgetItem("3rd Quart"))
        self.statisticsTable.setItem(8,0,QTableWidgetItem("IQR"))
        self.statisticsTable.setItem(9,0,QTableWidgetItem("Gini"))

    def setStats(self, stats, selection):
        #self.statisticsTable.clear()
        #self.__addStatsLabels()
        # update the interface
        for row in range(self.statisticsTable.rowCount()):
            label = self.statisticsTable.item(row,0).text()
            if stats.has_key(label):
                item = QTableWidgetItem(str(stats[label]))
                self.statisticsTable.setItem(row, 1, item)
            if selection:
                if selection.has_key(label):
                    item = QTableWidgetItem(str(selection[label]))
                    self.statisticsTable.setItem(row, 2, item)
            else:
                self.statisticsTable.setItem(row, 2, QTableWidgetItem(""))
        self.statisticsTable.horizontalHeader().setResizeMode(0, QHeaderView.ResizeToContents)
        self.statisticsTable.horizontalHeader().setResizeMode(1, QHeaderView.ResizeToContents)
        self.statisticsTable.horizontalHeader().setResizeMode(2, QHeaderView.Stretch)
        self.statisticsTable.resizeRowsToContents()

    def __clearStats(self):
        self.statisticsTable.clear()
        self.__addStatsLabels()
        self.statisticsProgressBar.setValue(0)

    def setStatsProgressBar(self, value):
        self.statisticsProgressBar.setValue(int(value))

    #
    # Charts group
    #
    def __lockDependentGroup(self, onoff):
        self.yaxisCombo.setDisabled(onoff)
        self.yaxisLabel.setDisabled(onoff)
        self.rLabel.setDisabled(onoff)
        self.pLabel.setDisabled(onoff)
        self.r2Label.setDisabled(onoff)
        self.lineLabel.setDisabled(onoff)
        if onoff:
            self.clearDependentValues()

    def __histogramSelected(self):
        self.__lockDependentGroup(True)
        self.curr_chart = 0
        self.clearPlot()
        self.chartChanged.emit()

    def __boxplotSelected(self):
        self.__lockDependentGroup(True)
        self.curr_chart = 1
        self.clearPlot()
        self.chartChanged.emit()

    def __scatterplotSelected(self):
        self.__lockDependentGroup(False)
        self.curr_chart = 2
        self.clearPlot()
        self.chartChanged.emit()

    def getChartType(self):
        return self.curr_chart

    def __setYAxisCombo(self, attributes):
        self.yaxisCombo.clear()
        self.yaxisCombo.addItems(attributes)
        self.yaxisCombo.setCurrentIndex(0)

    def yAxisChanged(self):
        if self.curr_chart == 2:
            self.dependentChanged.emit()

    def getYAxisAttribute(self):
        return self.yaxisCombo.currentIndex()

    def clearDependentValues(self):
        self.rLabel.setText("r:")
        self.pLabel.setText("p:")
        self.r2Label.setText("r2:")
        self.lineLabel.setText("line:")

    def setCorrelation(self, stats):
        self.rLabel.setText("r:"+str(stats["r"]))
        self.pLabel.setText("p:"+str(stats["p"]))
        self.r2Label.setText("r2:"+str(stats["r2"]))
        self.lineLabel.setText("line:"+str(stats["line"]))

    def clearPlot(self):
        if has_pyqtgraph:
            self.chartPlotWidget.clear()
        else:
            pass