package utilities;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Iterator;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

/**
 *  Utility class that expands BinnedData with a constructor that reads data from a source file
 *
 *  @author daniel, Adrian Carro
 */
public class BinnedDataDouble extends BinnedData<Double> {

    // Optional record of explicit bin edges read from a CSV file. These are only kept when the file really uses
    // variable-width bins; otherwise the legacy BinnedData first-bin-minimum and single-bin-width representation is used
    private ArrayList<Double> binLowerEdges;
    private ArrayList<Double> binUpperEdges;

    //------------------------//
    //----- Constructors -----//
    //------------------------//

    /**
     * Loads data from a .csv file. The file should be in the format {bin min, bin max, value}, with as many initial
     * rows as needed for comments but always marked with an initial "#" character
     *
     * @param filename Address of the file to read data from
     */
    public BinnedDataDouble(String filename) {
        super(0.0,0.0);
        binLowerEdges = new ArrayList<>();
        binUpperEdges = new ArrayList<>();
        try (BufferedReader buffReader = new BufferedReader(new FileReader(filename))) {
            // Skip initial comment lines keeping mark of previous position to return to if line is not comment
            buffReader.mark(1000); // 1000 is just the number of characters that can be read while preserving the mark
            String line = buffReader.readLine();
            while (line.charAt(0) == '#') {
                buffReader.mark(1000);
                line = buffReader.readLine();
            }
            buffReader.reset(); // Return to previous position (before reading the first line that was not a comment)
            // Pass advanced buffered reader to CSVFormat parser
            try (CSVParser parser = CSVFormat.EXCEL.parse(buffReader)) {
                Iterator<CSVRecord> records = parser.iterator();
                CSVRecord record;
                // Read through records
                if(records.hasNext()) {
                    record = records.next();
                    // Use the first record to set the first bin minimum and the bin width...
                    double lowerEdge = Double.valueOf(record.get(0));
                    double upperEdge = Double.valueOf(record.get(1));
                    this.setFirstBinMin(lowerEdge);
                    this.setBinWidth(upperEdge - getSupportLowerBound());
                    // ...before recording the explicit edges and actually adding it to the array
                    binLowerEdges.add(lowerEdge);
                    binUpperEdges.add(upperEdge);
                    add(Double.valueOf(record.get(2)));
                    while(records.hasNext()) {
                        record = records.next();
                        // Next records keep their own edges in case the CSV uses variable-width bins
                        binLowerEdges.add(Double.valueOf(record.get(0)));
                        binUpperEdges.add(Double.valueOf(record.get(1)));
                        add(Double.valueOf(record.get(2)));
                    }
                    // If the lower edges follow the original equal-width convention, discard the extra edge storage so
                    // existing input files keep their previous interpretation exactly
                    preserveLegacyEqualWidthBehaviourWhenPossible();
                }
            }
        } catch (IOException e) {
            System.out.println("Problem while loading data from " + filename
                    + " for creating a BinnedDataDouble object");
            e.printStackTrace();
        }
    }

    /**
     * This constructor creates a BinnedDataDouble object with a given first bin minimum and a given bin width, but
     * without reading any data. Thus, data is to be added manually via the add method of the ArrayList
     *
     * @param firstBinMin First bin minimum
     * @param binWidth Bin width
     */
    public BinnedDataDouble(double firstBinMin, double binWidth) {
        super(firstBinMin, binWidth);
        // Manually constructed binned data keeps the historical equal-width representation
        binLowerEdges = null;
        binUpperEdges = null;
    }

    // Return the lower edge for one bin, using explicit CSV edges only when the data requires them
    public double getBinLowerEdge(int index) {
        if (hasExplicitBinEdges()) return binLowerEdges.get(index);
        return getSupportLowerBound() + index*getBinWidth();
    }

    // Return the upper edge for one bin, using explicit CSV edges only when the data requires them
    public double getBinUpperEdge(int index) {
        if (hasExplicitBinEdges()) return binUpperEdges.get(index);
        return getSupportLowerBound() + (index + 1)*getBinWidth();
    }

    // Return the width for one bin. For equal-width data this is the same value as getBinWidth()
    public double getBinWidth(int index) {
        return getBinUpperEdge(index) - getBinLowerEdge(index);
    }

    // Return the midpoint for one bin, allowing downstream interpolation to work with variable-width data
    public double getBinCenter(int index) {
        return (getBinLowerEdge(index) + getBinUpperEdge(index)) / 2.0;
    }

    @Override
    public double getSupportUpperBound() {
        // Variable-width CSVs must use the final explicit upper edge rather than size()*firstBinWidth
        if (hasExplicitBinEdges() && !binUpperEdges.isEmpty()) return binUpperEdges.get(binUpperEdges.size() - 1);
        return super.getSupportUpperBound();
    }

    @Override
    public Double getBinAt(double val) {
        // Equal-width data keeps the original BinnedData lookup path
        if (!hasExplicitBinEdges()) return super.getBinAt(val);
        // Variable-width data is searched against explicit upper edges, with out-of-support values clamped to the ends
        if (val < getSupportLowerBound()) return get(0);
        for (int i = 0; i < size(); i++) {
            if (val < getBinUpperEdge(i)) return get(i);
        }
        return get(size() - 1);
    }

    private boolean hasExplicitBinEdges() {
        return binLowerEdges != null && binUpperEdges != null;
    }

    private void preserveLegacyEqualWidthBehaviourWhenPossible() {
        if (binLowerEdges.size() < 2) return;
        double width = getBinWidth();
        // Legacy input files are identified by lower edges that advance by the first bin width. Some old files contain
        // a wider final printed upper edge, but the model historically ignored it, so this keeps old outputs stable
        for (int i = 1; i < binLowerEdges.size(); i++) {
            double expectedLowerEdge = getSupportLowerBound() + i*width;
            if (Math.abs(binLowerEdges.get(i) - expectedLowerEdge) > 1.0e-9) return;
        }
        binLowerEdges = null;
        binUpperEdges = null;
    }
}
