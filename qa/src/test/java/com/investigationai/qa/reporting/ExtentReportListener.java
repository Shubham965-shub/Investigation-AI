package com.investigationai.qa.reporting;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;

import com.aventstack.extentreports.ExtentReports;
import com.aventstack.extentreports.ExtentTest;
import com.aventstack.extentreports.Status;
import com.aventstack.extentreports.reporter.ExtentSparkReporter;
import org.testng.ITestContext;
import org.testng.ITestListener;
import org.testng.ITestResult;

public class ExtentReportListener implements ITestListener {
    private static final Path REPORT_PATH = Path.of("target", "extent-report.html");
    private static final ExtentReports REPORT = createReport();
    private static final ThreadLocal<ExtentTest> CURRENT_TEST = new ThreadLocal<>();

    private static ExtentReports createReport() {
        new File("target").mkdirs();
        ExtentSparkReporter sparkReporter = new ExtentSparkReporter(REPORT_PATH.toString());
        sparkReporter.config().setDocumentTitle("InvestigationAI QA Report");
        sparkReporter.config().setReportName("InvestigationAI UI Automation Results");
        sparkReporter.config().setTimeStampFormat("yyyy-MM-dd HH:mm:ss");
        ExtentReports reports = new ExtentReports();
        reports.attachReporter(sparkReporter);
        reports.setSystemInfo("Application", "InvestigationAI");
        reports.setSystemInfo("Run ID", firstNonBlank(
                System.getProperty("qa.runId"), System.getenv("GITHUB_RUN_ID"),
                System.getenv("BUILD_NUMBER"), "local-" + runTimestamp()));
        reports.setSystemInfo("Environment", firstNonBlank(
                System.getProperty("qa.environment"), System.getenv("QA_ENV"),
                System.getenv("CI") == null ? "local" : "ci"));
        reports.setSystemInfo("Execution", firstNonBlank(
                System.getProperty("execution"), System.getenv("QA_EXECUTION"), "local"));
        reports.setSystemInfo("Browser", firstNonBlank(
                System.getProperty("browser"), System.getenv("QA_BROWSER"), "chrome"));
        reports.setSystemInfo("Java", System.getProperty("java.version", "unknown"));
        reports.setSystemInfo("OS", System.getProperty("os.name", "unknown") + " "
                + System.getProperty("os.version", ""));
        reports.setSystemInfo("Branch", firstNonBlank(
                System.getProperty("git.branch"), System.getenv("GITHUB_REF_NAME"),
                System.getenv("CI_COMMIT_REF_NAME"), "not provided"));
        reports.setSystemInfo("Commit", firstNonBlank(
                System.getProperty("git.commit"), System.getenv("GITHUB_SHA"),
                System.getenv("CI_COMMIT_SHA"), "not provided"));
        reports.setSystemInfo("Report generated", LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        return reports;
    }

    @Override
    public void onTestStart(ITestResult result) {
        String description = result.getMethod().getDescription();
        String qualifiedName = result.getTestClass().getName() + "." + result.getMethod().getMethodName();
        ExtentTest test = REPORT.createTest(result.getMethod().getMethodName(),
                description == null || description.isBlank() ? qualifiedName : description);
        test.assignCategory(result.getTestContext().getName());
        Arrays.stream(result.getMethod().getGroups())
                .filter(group -> group != null && !group.isBlank())
                .forEach(test::assignCategory);
        test.info("Test class: " + result.getTestClass().getName());
        test.info("Test method: " + result.getMethod().getMethodName());
        CURRENT_TEST.set(test);
    }

    @Override
    public void onTestSuccess(ITestResult result) {
        ExtentTest test = CURRENT_TEST.get();
        if (test != null) {
            test.log(Status.PASS, "Test passed");
        }
        CURRENT_TEST.remove();
    }

    @Override
    public void onTestFailure(ITestResult result) {
        ExtentTest test = CURRENT_TEST.get();
        if (test != null) {
            test.log(Status.FAIL, result.getThrowable());
            attachFailureScreenshot(test, result);
        }
        CURRENT_TEST.remove();
    }

    @Override
    public void onTestSkipped(ITestResult result) {
        ExtentTest test = CURRENT_TEST.get();
        if (test != null) {
            if (result.getThrowable() == null) {
                test.log(Status.SKIP, "Test skipped");
            } else {
                test.log(Status.SKIP, result.getThrowable());
            }
        }
        CURRENT_TEST.remove();
    }

    private static void attachFailureScreenshot(ExtentTest test, ITestResult result) {
        Object screenshotValue = result.getAttribute("failureScreenshot");
        if (!(screenshotValue instanceof String screenshotPath) || screenshotPath.isBlank()) {
            return;
        }

        Path screenshot = Path.of(screenshotPath).toAbsolutePath().normalize();
        Path reportDirectory = REPORT_PATH.toAbsolutePath().normalize().getParent();
        if (!Files.isRegularFile(screenshot)) {
            test.warning("Failure screenshot was not found: " + screenshotPath);
            return;
        }

        String reportRelativePath = reportDirectory.relativize(screenshot).toString()
                .replace(File.separatorChar, '/');
        test.addScreenCaptureFromPath(reportRelativePath, "Failure screenshot");
    }

    private static String firstNonBlank(String... values) {
        return Arrays.stream(values)
                .filter(value -> value != null && !value.isBlank())
                .findFirst()
                .orElse("not provided");
    }

    private static String runTimestamp() {
        return LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"));
    }

    @Override
    public void onFinish(ITestContext context) {
        REPORT.flush();
    }
}