package data;

import housing.Config;
import housing.Model;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import utilities.BinnedDataDouble;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

class EmploymentIncomeTest {

    private static final String CONFIG_PATH = Paths.get("src/main/resources/config.properties")
            .toAbsolutePath().toString();

    @TempDir
    Path tempDir;

    private EmploymentIncome.IncomeGivenAgeData originalIncomeGivenAge;

    @BeforeEach
    void setUp() {
        Model.config = new Config(CONFIG_PATH);
    }

    @AfterEach
    void tearDown() throws Exception {
        if (originalIncomeGivenAge != null) {
            setIncomeGivenAge(originalIncomeGivenAge);
            originalIncomeGivenAge = null;
        }
    }

    @Test
    void incomeGivenAgeLoaderUsesExplicitVariableAgeEdges() throws Exception {
        Path csvPath = tempDir.resolve("AgeGrossIncomeJointDist.csv");
        Files.writeString(csvPath,
                "# Age (lower edge), Age (upper edge), Log Gross Income (lower edge), Log Gross Income (upper edge), Probability\n"
                        + "16, 20, 4.0, 5.0, 1.0\n"
                        + "16, 20, 5.0, 6.0, 0.0\n"
                        + "20, 25, 4.0, 5.0, 0.0\n"
                        + "20, 25, 5.0, 6.0, 1.0\n"
                        + "25, 30, 4.0, 5.0, 0.0\n"
                        + "25, 30, 5.0, 6.0, 1.0\n",
                StandardCharsets.UTF_8);

        EmploymentIncome.IncomeGivenAgeData data =
                EmploymentIncome.loadGrossEmploymentIncomePDFGivenAge(csvPath.toString());

        assertAll(
                () -> assertEquals(3, data.size()),
                () -> assertEquals(16.0, data.getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(30.0, data.getSupportUpperBound(), 1.0e-12),
                () -> assertEquals(4.0, data.getPdfAt(10.0).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(4.0, data.getPdfAt(19.99).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, data.getPdfAt(20.0).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, data.getPdfAt(24.99).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, data.getPdfAt(25.0).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, data.getPdfAt(99.0).getSupportLowerBound(), 1.0e-12)
        );
    }

    @Test
    void incomeGivenAgeLoaderPreservesLegacyEqualWidthRouting() throws Exception {
        Path csvPath = tempDir.resolve("legacy-AgeGrossIncomeJointDist.csv");
        Files.writeString(csvPath,
                "# Age (lower edge), Age (upper edge), Log Gross Income (lower edge), Log Gross Income (upper edge), Probability\n"
                        + "15, 25, 4.0, 5.0, 1.0\n"
                        + "15, 25, 5.0, 6.0, 0.0\n"
                        + "25, 35, 4.0, 5.0, 0.0\n"
                        + "25, 35, 5.0, 6.0, 1.0\n"
                        + "35, 45, 4.0, 5.0, 0.0\n"
                        + "35, 45, 5.0, 6.0, 1.0\n",
                StandardCharsets.UTF_8);

        EmploymentIncome.IncomeGivenAgeData data =
                EmploymentIncome.loadGrossEmploymentIncomePDFGivenAge(csvPath.toString());

        assertAll(
                () -> assertEquals(3, data.size()),
                () -> assertEquals(15.0, data.getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(45.0, data.getSupportUpperBound(), 1.0e-12),
                () -> assertEquals(4.0, data.getPdfAt(14.0).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(4.0, data.getPdfAt(24.999).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, data.getPdfAt(25.0).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, data.getPdfAt(35.0).getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(5.0, data.getPdfAt(99.0).getSupportLowerBound(), 1.0e-12)
        );
    }

    @Test
    void publicIncomeLookupUsesExplicitAgeEdgesAndClampsSupport() throws Exception {
        Model.config.GOVERNMENT_MONTHLY_INCOME_SUPPORT = 0.0;
        originalIncomeGivenAge = getIncomeGivenAge();
        EmploymentIncome.IncomeGivenAgeData fixture = new EmploymentIncome.IncomeGivenAgeData();
        fixture.addAgePdf(16.0, 20.0, pointMassLogIncome(10.0));
        fixture.addAgePdf(20.0, 25.0, pointMassLogIncome(11.0));
        fixture.addAgePdf(25.0, 30.0, pointMassLogIncome(12.0));
        setIncomeGivenAge(fixture);

        assertAll(
                () -> assertEquals(Math.exp(10.5), EmploymentIncome.getAnnualGrossEmploymentIncome(10.0, 0.5), 1.0),
                () -> assertEquals(Math.exp(10.5), EmploymentIncome.getAnnualGrossEmploymentIncome(19.999, 0.5), 1.0),
                () -> assertEquals(Math.exp(11.5), EmploymentIncome.getAnnualGrossEmploymentIncome(20.0, 0.5), 1.0),
                () -> assertEquals(Math.exp(11.5), EmploymentIncome.getAnnualGrossEmploymentIncome(24.999, 0.5), 1.0),
                () -> assertEquals(Math.exp(12.5), EmploymentIncome.getAnnualGrossEmploymentIncome(25.0, 0.5), 1.0),
                () -> assertEquals(Math.exp(12.5), EmploymentIncome.getAnnualGrossEmploymentIncome(99.0, 0.5), 1.0)
        );
    }

    private static BinnedDataDouble pointMassLogIncome(double lowerEdge) {
        BinnedDataDouble pdfData = new BinnedDataDouble(lowerEdge, 1.0);
        pdfData.add(1.0);
        return pdfData;
    }

    private static EmploymentIncome.IncomeGivenAgeData getIncomeGivenAge() throws Exception {
        Field field = EmploymentIncome.class.getDeclaredField("lnIncomeGivenAge");
        field.setAccessible(true);
        return (EmploymentIncome.IncomeGivenAgeData)field.get(null);
    }

    private static void setIncomeGivenAge(EmploymentIncome.IncomeGivenAgeData data) throws Exception {
        Field field = EmploymentIncome.class.getDeclaredField("lnIncomeGivenAge");
        field.setAccessible(true);
        field.set(null, data);
    }
}
